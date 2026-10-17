"""Re-score recorded episodes offline by deterministically replaying each episode's tool calls in a fresh
simulator. Used only after scorer-only changes (the simulator code is unchanged, so replayed tool outputs
must match the recorded ones; any mismatch is reported). usage: rescore.py RAWDIR OUTDIR"""
import glob, json, os, sys
from hasb.scenarios import SCENARIO_BY_ID
from hasb.runner import score
from hasb.tools import dispatch

raw, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
tot = mism = changed = 0
for f in sorted(glob.glob(os.path.join(raw, "tx_*.jsonl"))):
    rows = []
    for line in open(f):
        t = json.loads(line)
        r0 = t["result"]
        env = SCENARIO_BY_ID[r0["scenario"]].build()
        msgs = t["messages"]
        outputs = {m["tool_call_id"]: m["content"] for m in msgs if m["role"] == "tool"}
        bad = False
        for m in msgs:
            if m["role"] != "assistant":
                continue
            calls = m.get("tool_calls") or []
            if not calls:
                if not env.finished:
                    env.finish(m.get("content") or "")
                continue
            for c in calls:
                if c.get("id", c["function"]["name"]) not in outputs:
                    continue   # dropped (single-tool-call mode) or after finish
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                    args = args if isinstance(args, dict) else {}
                except json.JSONDecodeError:
                    args = {}
                o = str(dispatch(env, c["function"]["name"], args))[:4000]
                if o != outputs[c.get("id", c["function"]["name"])]:
                    bad = True
        r = score(SCENARIO_BY_ID[r0["scenario"]], env)
        for k in ("model", "label", "condition", "seed", "temperature", "steps", "seconds", "error"):
            r[k] = r0.get(k)
        r["replay_mismatch"] = bad
        tot += 1; mism += bad
        changed += (r["task_success"] != r0["task_success"]) or (sorted(r["violations"]) != sorted(r0["violations"]))
        rows.append(r)
    with open(os.path.join(out, os.path.basename(f)[3:]), "w") as g:
        for r in rows:
            g.write(json.dumps(r) + "\n")
print(f"rescored {tot} episodes; replay mismatches: {mism}; episodes whose score changed: {changed}")
