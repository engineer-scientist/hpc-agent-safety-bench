"""Copy a run's results from Flare to results/raw/<run_id>/ through the IRI API (view, 5 MB chunks)."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from hasb.live import alcf_client as c
from alcf.build_job import FLARE
CH = 5 * 1024 * 1024

def fetch(remote, local):
    with open(local, "w") as f:
        off = 0
        while True:
            r = c.fs("view", "flare", params={"path": remote, "offset": off, "size": CH})
            out = (r.get("result") or {}).get("output") if isinstance(r, dict) else None
            if not out:
                print("  !", remote, str(r)[:200]); return False
            f.write(out["content"])
            n = out["end_position"] - out["start_position"]
            off += n
            if n < CH:
                return True

def main(run_id, sub="results", dest=None):
    dest = dest or os.path.join(ROOT, "results", "raw", run_id)
    os.makedirs(dest, exist_ok=True)
    for d in (sub, "logs"):
        base = f"{FLARE}/runs/{run_id}/{d}"
        ls = c.fs("ls", "flare", params={"path": base})
        for x in (ls.get("result") or {}).get("output", []):
            if x["type"] == "file":
                loc = os.path.join(dest, x["name"] if d == sub else "log_" + x["name"])
                ok = fetch(f"{base}/{x['name']}", loc)
                print(("ok " if ok else "ERR"), x["name"], x["size"])

if __name__ == "__main__":
    main(*sys.argv[1:])
