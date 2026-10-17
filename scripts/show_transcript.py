"""Print a compact view of transcripts. usage: tools_show.py RAWDIR MODEL SCENARIO [cond] [max]"""
import json, sys
raw, model, scen = sys.argv[1:4]
cond = sys.argv[4] if len(sys.argv) > 4 else None
mx = int(sys.argv[5]) if len(sys.argv) > 5 else 1
k = 0
for l in open(f"{raw}/tx_{model}.jsonl"):
    t = json.loads(l); r = t["result"]
    if r["scenario"] != scen or (cond and r["condition"] != cond):
        continue
    k += 1
    if k > mx: break
    print("#####", model, scen, r["condition"], r["seed"], "success", r["task_success"], r["violations"], "err", (r.get("error") or "")[-200:])
    for m in t["messages"][2:]:
        if m["role"] == "assistant":
            print("  A:", (m.get("content") or "")[:250].replace("\n", " "),
                  [(c["function"]["name"], c["function"]["arguments"][:300]) for c in m.get("tool_calls", [])])
        elif m["role"] == "tool":
            print("  T:", m["content"][:160].replace("\n", " | "))
