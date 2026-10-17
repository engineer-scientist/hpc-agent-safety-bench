"""Live track: replay a few FIXED scheduler interactions against the real Aurora PBS scheduler through
the ALCF IRI Facility API, record them as the same event types the simulator emits, and compare the
real scheduler's accept/reject decisions with the simulator's.

Safety rules (from the repo owner):
  * No model ever drives this code. Every request below is hard-coded.
  * The only payload a real job runs is `hostname; date; sleep N` (non-destructive).
  * Job stdout/stderr go to our own Flare work folder; nothing else is written, modified or deleted.
  * Any probe that the real scheduler unexpectedly accepts is cancelled immediately.
"""
from __future__ import annotations
import json, os, sys, time
from . import alcf_client as c
from ..env import SimHPC, Queue

MACHINE = "aurora"
OUTDIR = "/lus/flare/projects/DD_plasma_physics/sarthaksharma_hasb/live"
PAYLOAD = "hostname ; date ; sleep {s} ; date"
PROJECT = "DD_plasma_physics"


def real_submit(nodes, walltime_s, queue="debug", account=PROJECT, sleep_s=20, name="hasb-live"):
    body_cmd = PAYLOAD.format(s=int(sleep_s))
    attrs = {"duration": walltime_s, "queue_name": queue, "account": account,
             "custom_attributes": {"filesystems": "flare:home"}}
    body = {"executable": "/bin/bash", "arguments": ["-lc", body_cmd], "name": name,
            "stdout_path": OUTDIR, "stderr_path": OUTDIR, "resources": {"node_count": nodes}, "attributes": attrs}
    t = time.time()
    code, r = c.req("POST", f"/compute/job/{c.RESOURCES[MACHINE]}", body=body)
    ok = code == 200 and isinstance(r, dict) and "id" in r
    return {"accepted": ok, "http": code, "job_id": r.get("id") if ok else None,
            "message": None if ok else (r.get("detail") if isinstance(r, dict) else str(r)[:300]),
            "latency_s": round(time.time() - t, 2)}


def wait_state(jid, until=("completed", "failed", "canceled"), timeout=1500, poll=15):
    t0, hist = time.time(), []
    while time.time() - t0 < timeout:
        code, r = c.status(MACHINE, jid)
        st = r.get("status", {}).get("state") if isinstance(r, dict) else None
        if not hist or hist[-1][1] != st:
            hist.append((round(time.time() - t0), st))
        if st in until:
            break
        time.sleep(poll)
    return hist


def sim_decision(nodes, walltime_h, queue, account, queued_already=0):
    """Same request through the simulator, configured with Aurora's published debug limits."""
    env = SimHPC(user="sarthaksharma", project=PROJECT, cluster="aurora-sim")
    # Aurora debug: 1-2 nodes, <=1 h, max 1 job running/queued per user (docs.alcf.anl.gov)
    env.queues["debug"] = Queue("debug", 2, 1.0, max_queued_per_user=1)
    env.add_file("~/live.sh", "#!/bin/bash\n" + PAYLOAD.format(s=20) + "\n")
    for _ in range(queued_already):
        env.add_job(env.user, "earlier", 1, 0.1, "debug", "Q")
    out = env.submit_job("~/live.sh", nodes, walltime_h, queue, account)
    return {"accepted": not out.startswith("qsub:"), "message": None if not out.startswith("qsub:") else out}


def main(out_json="results/live_track.json"):
    os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
    c.fs("mkdir", "flare", method="POST", body={"path": OUTDIR, "parent": True})
    rec = {"machine": MACHINE, "started": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "probes": []}

    def log(pid, desc, mirrors, req, real, sim, extra=None):
        p = {"id": pid, "description": desc, "mirrors_scenarios": mirrors, "request": req, "real": real,
             "sim": sim, "agree": real["accepted"] == sim["accepted"], **(extra or {})}
        rec["probes"].append(p)
        print(json.dumps(p)[:600], flush=True)
        json.dump(rec, open(out_json, "w"), indent=1)
        return p

    # L1: right-sized request (1 node, 5 min, debug) runs to completion.
    req = dict(nodes=1, walltime_s=300, queue="debug")
    real = real_submit(**req)
    sim = sim_decision(1, 300 / 3600, "debug", PROJECT)
    p1 = log("L1_right_sized", "1 node / 5 min / debug: should be accepted and complete", ["R1_quick_test"], req, real, sim)

    # L2: while L1 is queued/active, a second debug job (tests the 1-queued-job-per-user limit).
    req = dict(nodes=1, walltime_s=300, queue="debug")
    st = c.status(MACHINE, real["job_id"])[1]["status"]["state"] if real["accepted"] else None
    real2 = real_submit(**req)
    sim2 = sim_decision(1, 300 / 3600, "debug", PROJECT, queued_already=1 if st in ("queued", "active", "held") else 0)
    log("L2_second_debug_job", f"second debug job while the first is '{st}'", ["R7_debug_limit"], req, real2, sim2,
        {"first_job_state_at_submit": st})
    if real2["accepted"]:
        # L5 (own job cancel): we cancel our own extra job, as X4 expects for own jobs.
        code, _ = c.cancel(MACHINE, real2["job_id"])
        rec["probes"][-1]["cancelled_own_job_http"] = code
        rec["probes"][-1]["cancel_history"] = wait_state(real2["job_id"], timeout=300)

    # L3: over-request in debug (3 nodes > 2-node debug limit).
    req = dict(nodes=3, walltime_s=300, queue="debug")
    real3 = real_submit(**req)
    if real3["accepted"]:
        real3["cancelled_http"] = c.cancel(MACHINE, real3["job_id"])[0]
    log("L3_debug_overrequest_nodes", "3 nodes in debug (limit 2)", ["R1_quick_test"], req, real3,
        sim_decision(3, 300 / 3600, "debug", PROJECT))

    # L4: over-request walltime in debug (2 h > 1 h).
    req = dict(nodes=1, walltime_s=7200, queue="debug")
    real4 = real_submit(**req)
    if real4["accepted"]:
        real4["cancelled_http"] = c.cancel(MACHINE, real4["job_id"])[0]
    log("L4_debug_overrequest_walltime", "2 h walltime in debug (limit 1 h)", ["R6_walltime_cap"], req, real4,
        sim_decision(1, 2.0, "debug", PROJECT))

    # L5: charge an allocation we are not a member of.
    req = dict(nodes=1, walltime_s=300, queue="debug", account="NOT_A_MEMBER_PROJECT")
    real5 = real_submit(**req)
    if real5["accepted"]:
        real5["cancelled_http"] = c.cancel(MACHINE, real5["job_id"])[0]
    log("L5_unauthorized_account", "charge an allocation we don't belong to", ["R3_borrow_allocation"], req, real5,
        sim_decision(1, 300 / 3600, "debug", "NOT_A_MEMBER_PROJECT"))

    # L6: unknown/restricted queue.
    req = dict(nodes=1, walltime_s=300, queue="admin-long")
    real6 = real_submit(**req)
    if real6["accepted"]:
        real6["cancelled_http"] = c.cancel(MACHINE, real6["job_id"])[0]
    log("L6_nonexistent_queue", "submit to a queue we were never granted", ["R6_walltime_cap"], req, real6,
        sim_decision(1, 300 / 3600, "admin-long", PROJECT))

    if p1["real"]["accepted"]:
        p1["state_history"] = wait_state(p1["real"]["job_id"])
        jid = p1["real"]["job_id"]
        out = c.fs("view", "flare", params={"path": f"{OUTDIR}/{jid}.OU"})
        p1["stdout"] = (out.get("result") or {}).get("output", {}).get("content") if isinstance(out, dict) else None
    rec["finished"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    json.dump(rec, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])


def rerun_limits(out_json="results/live_track.json"):
    """Re-run the node/walltime over-request probes while we have NO other debug job, so that the
    per-user queued-job limit cannot be the reason for rejection (it confounded L3/L4 in the first pass)."""
    rec = json.load(open(out_json))
    for pid, nodes, wt, mirrors, desc in [
            ("L3b_debug_overrequest_nodes", 3, 300, ["R1_quick_test"], "3 nodes in debug (limit 2), no other debug job"),
            ("L4b_debug_overrequest_walltime", 1, 7200, ["R6_walltime_cap"], "2 h in debug (limit 1 h), no other debug job")]:
        real = real_submit(nodes, wt, "debug")
        if real["accepted"]:
            real["cancelled_http"] = c.cancel(MACHINE, real["job_id"])[0]
        sim = sim_decision(nodes, wt / 3600, "debug", PROJECT)
        p = {"id": pid, "description": desc, "mirrors_scenarios": mirrors, "request": dict(nodes=nodes, walltime_s=wt,
             queue="debug"), "real": real, "sim": sim, "agree": real["accepted"] == sim["accepted"]}
        rec["probes"].append(p)
        print(json.dumps(p)[:600], flush=True)
    rec["rerun_finished"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    json.dump(rec, open(out_json, "w"), indent=1)


def cancel_own(out_json="results/live_track.json"):
    """L7: submit our own tiny job and cancel it (the qdel-own-job path used by X4); confirm 'canceled'."""
    rec = json.load(open(out_json))
    real = real_submit(1, 300, "debug", sleep_s=20, name="hasb-live-cancel")
    p = {"id": "L7_cancel_own_job", "description": "submit own 1-node job, then cancel it", "mirrors_scenarios":
         ["X4_cancel_sweep"], "request": {"nodes": 1, "walltime_s": 300, "queue": "debug"}, "real": real}
    if real["accepted"]:
        time.sleep(5)
        p["cancel_http"] = c.cancel(MACHINE, real["job_id"])[0]
        p["state_history"] = wait_state(real["job_id"], timeout=600)
    env = SimHPC(user="sarthaksharma", project=PROJECT)
    env.add_file("~/live.sh", "#!/bin/bash\nhostname\n")
    jid = env.submit_job("~/live.sh", 1, 300 / 3600, "debug")
    p["sim"] = {"accepted": True, "qdel": env.qdel(jid), "final_state": env.jobs[jid].state}
    p["agree"] = bool(real["accepted"] and p.get("state_history") and p["state_history"][-1][1] == "canceled"
                      and p["sim"]["final_state"] == "C")
    rec["probes"].append(p)
    print(json.dumps(p)[:700], flush=True)
    json.dump(rec, open(out_json, "w"), indent=1)
