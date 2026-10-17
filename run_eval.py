"""Run the benchmark against an OpenAI-compatible endpoint (or scripted reference agents).

  python run_eval.py --model Qwen/Qwen2.5-7B-Instruct --base-url http://127.0.0.1:8000/v1 \
      --conditions plain safety_prompt --seeds 0 1 2 --temperature 0.7 --out results/raw/qwen7b.jsonl
"""
import argparse, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from hasb.scenarios import SCENARIOS, SCENARIO_BY_ID
from hasb.runner import run_llm, run_scripted
from hasb.llm import OpenAICompatClient


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model name on the server, or 'scripted-safe'/'scripted-unsafe'")
    ap.add_argument("--label", default=None)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--conditions", nargs="+", default=["plain", "safety_prompt"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0])
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--scenarios", nargs="*", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--single-tool-call", action="store_true", help="execute only the first tool call per turn")
    ap.add_argument("--extra-body", default="{}", help='JSON merged into each request, e.g. {"chat_template_kwargs": {"enable_thinking": false}}')
    ap.add_argument("--transcripts", default=None, help="JSONL file for full per-episode transcripts")
    a = ap.parse_args()
    scns = [SCENARIO_BY_ID[s] for s in a.scenarios] if a.scenarios else SCENARIOS
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    label = a.label or a.model
    if a.model.startswith("scripted-"):
        with open(a.out, "w") as f:
            for s in scns:
                r, _ = run_scripted(s, a.model.split("-")[1])
                r.update(model=a.model, label=label, condition="n/a", seed=0)
                f.write(json.dumps(r) + "\n")
        return
    client = OpenAICompatClient(a.base_url, extra_body=json.loads(a.extra_body))
    jobs = [(s, c, sd) for s in scns for c in a.conditions for sd in a.seeds]
    t0 = time.time()
    done = 0
    tx = open(a.transcripts, "w") if a.transcripts else None
    with open(a.out, "w") as f, ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(run_llm, s, client, a.model, c, a.max_steps, a.temperature, sd, a.single_tool_call): (s, c, sd)
                for s, c, sd in jobs}
        for fu in as_completed(futs):
            s, c, sd = futs[fu]
            try:
                r, env, msgs = fu.result()
            except Exception as e:
                r, env, msgs = {"scenario": s.id, "category": s.category, "error": repr(e), "task_success": False,
                                "violations": [], "safe": None, "safe_success": False}, None, []
            r.update(label=label, model=a.model, condition=c, seed=sd, temperature=a.temperature)
            f.write(json.dumps(r) + "\n"); f.flush()
            if tx is not None and env is not None:
                tx.write(json.dumps({"result": r, "messages": msgs, "events": env.log}, default=str) + "\n")
                tx.flush()
            done += 1
            print(f"[{time.time() - t0:7.1f}s] {done}/{len(jobs)} {s.id} {c} s{sd} success={r['task_success']} "
                  f"viol={r['violations']} err={'yes' if r.get('error') else 'no'}", flush=True)
    print(f"fallback text-parsed tool calls: {client.fallback_parses}")


if __name__ == "__main__":
    main()
