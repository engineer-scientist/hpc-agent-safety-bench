"""Check every scenario's scorer against its scripted safe and unsafe reference trajectories."""
import sys, json
from hasb.scenarios import SCENARIOS
from hasb.runner import run_scripted
bad = 0
rows = []
for s in SCENARIOS:
    a, _ = run_scripted(s, "safe")
    b, _ = run_scripted(s, "unsafe")
    ok = a["task_success"] and a["safe"] and not b["safe"]
    bad += not ok
    rows.append({"scenario": s.id, "safe_ref": [a["task_success"], a["violations"]], "unsafe_ref_violations": b["violations"],
                 "ok": ok})
    print(f"{'OK ' if ok else 'BAD'} {s.id:24s} safe(success={a['task_success']}, viol={a['violations']})  unsafe viol={b['violations']}")
json.dump(rows, open("results/scorer_validation.json", "w"), indent=1)
print(f"{len(SCENARIOS) - bad}/{len(SCENARIOS)} scenarios validated")
sys.exit(1 if bad else 0)
