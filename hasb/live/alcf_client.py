"""Minimal client for the ALCF IRI Facility API (https://api.alcf.anl.gov).

Token acquisition is delegated to ALCF's helper script (alcf_facility_api_globus_token.py);
set ALCF_TOKEN_CMD to a command that prints a valid access token, or ALCF_TOKEN directly.
"""
from __future__ import annotations
import json, os, shlex, subprocess, time, urllib.request, urllib.error, urllib.parse

API = os.environ.get("ALCF_API", "https://api.alcf.anl.gov/api/v1")
RESOURCES = {
    "aurora": "0325fc07-6fb7-4453-b772-3d5030b2df72",
    "polaris": "55c1c993-1124-47f9-b823-514ba3849a9a",
    "home": "6115bd2c-957a-4543-abff-5fae52992ff2",
    "flare": "154bb3be-5d12-4a76-a16b-898b8e310a4b",
    "eagle": "1c3ad9d4-2e91-42bc-becb-72b1fde1235c",
}
_tok = None

def token() -> str:
    global _tok
    if _tok and _tok[1] > time.time():
        return _tok[0]
    t = os.environ.get("ALCF_TOKEN")
    if not t:
        # Set ALCF_TOKEN, or ALCF_TOKEN_CMD to a command that prints a fresh access token, e.g. ALCF's
        # "python alcf_facility_api_globus_token.py get_access_token" helper (see docs.alcf.anl.gov/services/iri-api/).
        cmd = os.environ.get("ALCF_TOKEN_CMD")
        if not cmd:
            raise RuntimeError("set ALCF_TOKEN or ALCF_TOKEN_CMD (command that prints an ALCF IRI API access token)")
        t = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    _tok = (t, time.time() + 600)
    return t

def req(method: str, path: str, body=None, params=None, raw=False, timeout=120):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", f"Bearer {token()}")
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            b = resp.read()
            if raw:
                return resp.status, b
            return resp.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b)
        except Exception:
            return e.code, b.decode(errors="replace")

def wait_task(task_id: str, timeout=300, poll=3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, t = req("GET", f"/task/{task_id}")
        st = (t or {}).get("status") if isinstance(t, dict) else None
        if st in ("completed", "failed", "canceled"):
            return t
        time.sleep(poll)
    return {"status": "timeout", "id": task_id}

def fs(op: str, fs_name: str, method="GET", params=None, body=None):
    """Run an async filesystem op and wait for its task result."""
    code, r = req(method, f"/filesystem/{op}/{RESOURCES[fs_name]}", body=body, params=params)
    if isinstance(r, dict) and "task_id" in r:
        return wait_task(r["task_id"])
    if isinstance(r, str) and len(r) < 80:
        return wait_task(r.strip('"'))
    return {"http": code, "body": r}

def submit(machine: str, script: str, name: str, nodes=1, walltime_s=300, queue="debug",
           filesystems=None, stdout_dir=None, extra_attrs=None):
    fsys = filesystems or ("home:eagle" if machine == "polaris" else "flare:home")
    out = stdout_dir or "/home/sarthaksharma"
    attrs = {"duration": walltime_s, "queue_name": queue, "account": "DD_plasma_physics",
             "custom_attributes": {"filesystems": fsys, **(extra_attrs or {})}}
    body = {"executable": "/bin/bash", "arguments": ["-lc", script], "name": name,
            "stdout_path": out, "stderr_path": out,
            "resources": {"node_count": nodes}, "attributes": attrs}
    return req("POST", f"/compute/job/{RESOURCES[machine]}", body=body)

def status(machine: str, job_id: str):
    return req("GET", f"/compute/status/{RESOURCES[machine]}/{job_id}", params={"historical": "true"})

def list_jobs(machine: str, limit=20):
    return req("POST", f"/compute/status/{RESOURCES[machine]}", body={"owner": "sarthaksharma"},
               params={"historical": "true", "limit": limit})

def cancel(machine: str, job_id: str):
    return req("DELETE", f"/compute/cancel/{RESOURCES[machine]}/{job_id}")
