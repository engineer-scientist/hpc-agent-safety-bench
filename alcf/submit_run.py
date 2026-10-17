"""Submit a benchmark run (spec JSON) to Aurora through the ALCF IRI API and record the job id.
usage: python alcf/submit_run.py alcf/runs/<spec>.json"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from hasb.live import alcf_client as c
from alcf.build_job import build, build_stage, FLARE
spec = json.load(open(sys.argv[1]))
if "--stage" in sys.argv:
    sarg, sdir = build_stage()
    st = c.fs("ls", "flare", params={"path": sdir})
    if st.get("status") == "completed" and any(x["name"] == "DONE" for x in st["result"]["output"]):
        print("code already staged at", sdir)
    else:
        code, r = c.submit("aurora", sarg, "hasb-stage", nodes=1, walltime_s=300, queue="debug", stdout_dir=FLARE)
        print("stage job:", code, r if code != 403 else "blocked by API firewall")
arg, run_dir = build(spec["run_id"], spec["models"], spec["eval_args"], spec["minutes"])
code, r = c.submit("aurora", arg, "hasb-" + spec["run_id"], nodes=1, walltime_s=spec["walltime_s"],
                   queue=spec.get("queue", "debug"), stdout_dir=FLARE)
print(code, r if code != 403 else "blocked by API firewall")
if code == 200:
    with open(os.path.join(ROOT, "alcf", "submitted_jobs.jsonl"), "a") as f:
        f.write(json.dumps({"run_id": spec["run_id"], "job_id": r["id"], "run_dir": run_dir, "spec": spec}) + "\n")
