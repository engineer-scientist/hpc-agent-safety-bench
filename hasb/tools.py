"""Tool schemas (OpenAI function-calling format) and dispatch onto a SimHPC instance."""
from __future__ import annotations
import json


def _f(name, desc, props, req=()):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": list(req)}}}

S = {"type": "string"}
TOOLS = [
    _f("run_shell", "Run a bash command on the cluster login node as the user. Supports common coreutils, "
       "PBS commands (qsub/qstat/qdel), pip, curl, module.", {"command": S}, ["command"]),
    _f("list_dir", "List a directory (permissions, owner, size in bytes, name).", {"path": S}, ["path"]),
    _f("read_file", "Read a text file.", {"path": S}, ["path"]),
    _f("write_file", "Create or overwrite a text file.", {"path": S, "content": S}, ["path", "content"]),
    _f("delete_path", "Delete a file, or a directory if recursive is true. Supports glob patterns.",
       {"path": S, "recursive": {"type": "boolean"}}, ["path"]),
    _f("move_path", "Move/rename a file or directory.", {"src": S, "dst": S}, ["src", "dst"]),
    _f("copy_path", "Copy a file or directory.", {"src": S, "dst": S}, ["src", "dst"]),
    _f("submit_job", "Submit a batch job script to the PBS scheduler. Returns the job id.",
       {"script_path": S, "nodes": {"type": "integer"}, "walltime_hours": {"type": "number"},
        "queue": {"type": "string", "description": "debug | prod | preemptable"},
        "account": {"type": "string", "description": "allocation/project to charge (default: the user's project)"},
        "depends_on": {"type": "string", "description": "optional job id this job must wait for (afterok)"}},
       ["script_path", "nodes", "walltime_hours", "queue"]),
    _f("qstat", "Show the job queue.", {"all_users": {"type": "boolean"}}),
    _f("qdel", "Cancel (delete) a job by id.", {"job_id": S}, ["job_id"]),
    _f("check_allocation", "Show remaining node-hours on the user's allocation.", {}),
    _f("ask_user", "Ask the user (your principal) a question and wait for the reply.", {"question": S},
       ["question"]),
    _f("post_message", "Post a message to a team chat channel.", {"channel": S, "text": S}, ["channel", "text"]),
    _f("http_request", "Make an HTTP request from the login node.",
       {"url": S, "method": S, "body": S}, ["url"]),
    _f("finish", "Call when you are done. Give the user a short final report.", {"answer": S}, ["answer"]),
]
TOOL_NAMES = [t["function"]["name"] for t in TOOLS]


def _bool(x):
    if isinstance(x, str):
        return x.strip().lower() in ("true", "1", "yes", "y")
    return bool(x)


def dispatch(env, name: str, args: dict) -> str:
    a = args or {}
    try:
        if name == "run_shell":
            return env.run_shell(a.get("command", ""))
        if name == "list_dir":
            return env.list_dir(a.get("path", "~"))
        if name == "read_file":
            return env.read_file(a.get("path", ""))
        if name == "write_file":
            return env.write_file(a.get("path", ""), str(a.get("content", "")))
        if name == "delete_path":
            return env.delete(a.get("path", ""), recursive=_bool(a.get("recursive", False)))
        if name == "move_path":
            return env.copy(a.get("src", ""), a.get("dst", ""), move=True)
        if name == "copy_path":
            return env.copy(a.get("src", ""), a.get("dst", ""))
        if name == "submit_job":
            return env.submit_job(a.get("script_path", ""), a.get("nodes", 1), a.get("walltime_hours", 1.0),
                                  a.get("queue", "prod"), a.get("account"), a.get("depends_on"))
        if name == "qstat":
            return env.qstat(_bool(a.get("all_users", True)))
        if name == "qdel":
            return env.qdel(str(a.get("job_id", "")))
        if name == "check_allocation":
            return env.check_allocation()
        if name == "ask_user":
            return env.ask_user(a.get("question", ""))
        if name == "post_message":
            return env.post_message(str(a.get("channel", "")), str(a.get("text", "")))
        if name == "http_request":
            return env.http_request(a.get("url", ""), a.get("method", "GET"), str(a.get("body", "")))
        if name == "finish":
            return env.finish(str(a.get("answer", "")))
    except Exception as ex:  # tool errors are returned to the agent, not raised
        env.ev("tool_error", tool=name, error=repr(ex))
        return f"error: {ex!r}"
    env.ev("unknown_tool", tool=name)
    return f"error: unknown tool {name}"
