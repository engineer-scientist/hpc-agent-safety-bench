"""Poll a job until it leaves the queue/finishes, printing state changes. usage: watch.py JOBID [max_s] [until_state]"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hasb.live import alcf_client as c
jid, mx = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 700
until = sys.argv[3].split(",") if len(sys.argv) > 3 else ["completed", "failed", "canceled"]
t0, last = time.time(), None
while time.time() - t0 < mx:
    st = c.status("aurora", jid)[1].get("status", {}).get("state")
    if st != last:
        print(time.strftime("%H:%M:%S"), st, flush=True); last = st
    if st in until: break
    time.sleep(20)
