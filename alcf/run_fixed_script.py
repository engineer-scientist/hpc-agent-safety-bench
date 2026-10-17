"""Submit one of this repo's own fixed scripts to Aurora via the IRI API (debug queue).
The script is written into our Flare work folder and executed there; stdout/stderr also land there.
usage: python alcf/run_fixed_script.py alcf/probe_aurora.sh [walltime_s]"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from hasb.live import alcf_client as c
from alcf.encode import write_cmd, for_api
from alcf.build_job import FLARE
src = sys.argv[1]
wt = int(sys.argv[2]) if len(sys.argv) > 2 else 600
name = os.path.basename(src)
cmd = f"mkdir -p {FLARE}/scripts ; " + write_cmd(f"{FLARE}/scripts/{name}", open(src).read()) + \
      f" ; bash {FLARE}/scripts/{name}"
code, r = c.submit("aurora", for_api(cmd), "hasb-" + name.split(".")[0], walltime_s=wt, queue="debug", stdout_dir=FLARE)
print(code, r if code != 403 else "blocked by API firewall")
