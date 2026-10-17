"""Build a self-contained Aurora batch command for one benchmark run.

The ALCF IRI API has no file upload yet and turns newlines in job arguments into command separators,
so the job argument is a single line that (1) writes this repo's benchmark code plus a driver script
``job.sh`` into a run directory on Flare with printf, then (2) runs ``bash job.sh``. The driver serves
each model with vLLM on its own Intel GPU tile(s), runs the benchmark against every server in
parallel, and leaves results on Flare, where the API can read them back.
"""
from __future__ import annotations
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from alcf.encode import write_cmd, for_api

FLARE = "/lus/flare/projects/DD_plasma_physics/sarthaksharma_hasb"
CODE = ["hasb/__init__.py", "hasb/env.py", "hasb/tools.py", "hasb/scoring.py", "hasb/scenarios.py",
        "hasb/runner.py", "hasb/llm.py", "run_eval.py"]


def driver(run_dir, models, eval_args, minutes):
    L = ["#!/bin/bash", f"RD={run_dir}", "cd $RD/code",
         "md5sum " + " ".join(CODE) + " > $RD/logs/code_md5.txt",
         "module load frameworks",
         "export ZE_FLAT_DEVICE_HIERARCHY=FLAT CCL_PROCESS_LAUNCHER=none",
         "export HF_HOME=/flare/datasets/model-weights HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
         "export TMPDIR=/tmp RAY_TMPDIR=/tmp no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1",
         "echo start $(date +%s) $(hostname) > $RD/logs/timing.txt",
         "python -c 'import vllm; print(vllm.__version__)' > $RD/logs/vllm_version.txt 2>&1",
         "wait_ready() { for k in $(seq 1 200); do curl -s -m 5 http://127.0.0.1:$1/v1/models > /dev/null && return 0; sleep 10; done; return 1; }",
         "EVAL_PIDS=''"]
    for i, m in enumerate(models):
        port, lab = 8100 + i, m["label"]
        tiles = ",".join(map(str, m["tiles"]))
        src = m["hf_id"]
        pre = ""
        if m.get("download"):
            src = f"{FLARE}/models/{m['hf_id'].split('/')[-1]}"
            pre = (f"[ -f {src}/config.json ] || HF_HUB_OFFLINE=0 HF_HOME=$RD/hfcache "
                   f"https_proxy=http://proxy.alcf.anl.gov:3128 http_proxy=http://proxy.alcf.anl.gov:3128 "
                   f"bash -c 'hf download {m['hf_id']} --local-dir {src} || huggingface-cli download {m['hf_id']} --local-dir {src}' > $RD/logs/download_{lab}.log 2>&1 ; "
                   f"echo downloaded_{lab} $? $(date +%s) >> $RD/logs/timing.txt ; ")
        if m.get("pip"):
            pre += (f"https_proxy=http://proxy.alcf.anl.gov:3128 http_proxy=http://proxy.alcf.anl.gov:3128 "
                    f"python -m pip install --target $RD/pylib {m['pip']} > $RD/logs/pip_{lab}.log 2>&1 ; "
                    f"export PYTHONPATH=$RD/pylib ; ")
        if m.get("serve_env"):
            pre += f"export {m['serve_env']} ; "
        L.append(f"( {pre}ZE_AFFINITY_MASK={tiles} vllm serve {src} --served-model-name {lab} --port {port} "
                 f"--dtype bfloat16 --enforce-eager --tensor-parallel-size {len(m['tiles'])} "
                 f"--max-model-len {m.get('max_len', 16384)} --gpu-memory-utilization 0.85 "
                 f"--enable-auto-tool-choice --tool-call-parser {m['parser']} {m.get('extra', '')} "
                 f"> $RD/logs/vllm_{lab}.log 2>&1 ) &")
        L.append("SERVER_PIDS=\"${SERVER_PIDS:-} $!\"")
    for i, m in enumerate(models):
        port, lab = 8100 + i, m["label"]
        L += [f"( if wait_ready {port}; then",
              f"    echo ready_{lab} $(date +%s) >> $RD/logs/timing.txt",
              f"    timeout {minutes}m python run_eval.py --model {lab} --label {lab} --base-url http://127.0.0.1:{port}/v1 "
              f"{eval_args} {m.get('eval_extra', '')} --out $RD/results/{lab}.jsonl --transcripts $RD/results/tx_{lab}.jsonl > $RD/logs/eval_{lab}.log 2>&1",
              f"    echo done_{lab} $? $(date +%s) >> $RD/logs/timing.txt",
              f"  else echo notready_{lab} $(date +%s) >> $RD/logs/timing.txt; fi ) &",
              "EVAL_PIDS=\"$EVAL_PIDS $!\""]
    L += ["for p in $EVAL_PIDS; do wait $p; done",
          "cp $RD/logs/timing.txt $RD/results/ 2>/dev/null",
          "echo end $(date +%s) >> $RD/logs/timing.txt",
          # kill only our server process trees (pkill -f 'vllm serve' would also match this job's own
          # command line, which contains that text, and end the job with exit 143)
          "for p in $SERVER_PIDS; do pkill -TERM -P $p; kill $p 2>/dev/null; done", "exit 0"]
    return "\n".join(L) + "\n"


PART_A = ["hasb/__init__.py", "hasb/env.py", "hasb/tools.py", "hasb/scoring.py", "hasb/runner.py", "hasb/llm.py",
          "run_eval.py"]
PART_B = ["hasb/scenarios.py"]
MAX_ARG = 80000   # the API/PBS path truncates job arguments somewhere above ~90 kB


def code_hash():
    import hashlib
    h = hashlib.sha1()
    for f in PART_A:
        h.update(open(os.path.join(ROOT, f), "rb").read())
    return h.hexdigest()[:10]


def build_stage():
    """Job argument that writes PART_A into a content-addressed folder on Flare."""
    d = f"{FLARE}/code_{code_hash()}"
    parts = [f"mkdir -p {d}/hasb"]
    for f in PART_A:
        parts.append(write_cmd(f"{d}/{f}", open(os.path.join(ROOT, f)).read()))
    parts.append(f"touch {d}/DONE")
    arg = for_api(" ; ".join(parts))
    assert len(arg) < MAX_ARG, len(arg)
    return arg, d


def build(run_id, models, eval_args, minutes):
    run_dir = f"{FLARE}/runs/{run_id}"
    stage = f"{FLARE}/code_{code_hash()}"
    parts = [f"mkdir -p {run_dir}/code/hasb {run_dir}/results {run_dir}/logs"]
    for f in PART_B:
        parts.append(write_cmd(f"{run_dir}/code/{f}", open(os.path.join(ROOT, f)).read()))
    parts.append(write_cmd(f"{run_dir}/job.sh", driver(run_dir, models, eval_args, minutes)))
    parts.append(f"for k in $(seq 1 180); do [ -f {stage}/DONE ] && break; sleep 10; done")
    parts.append(f"cp -r {stage}/hasb {stage}/run_eval.py {run_dir}/code/")
    parts.append(f"bash {run_dir}/job.sh > {run_dir}/logs/job.log 2>&1")
    arg = for_api(" ; ".join(parts))
    assert len(arg) < MAX_ARG, len(arg)
    return arg, run_dir
