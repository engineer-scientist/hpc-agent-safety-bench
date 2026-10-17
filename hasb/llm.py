"""Tiny OpenAI-compatible chat client (stdlib only) for vLLM servers, with a fallback parser
for models that print tool calls as text instead of using the structured field."""
from __future__ import annotations
import json, re, time, urllib.request, uuid


class OpenAICompatClient:
    def __init__(self, base_url="http://127.0.0.1:8000/v1", api_key="EMPTY", max_tokens=1536, timeout=600,
                 extra_body=None):
        self.base, self.key, self.max_tokens, self.timeout = base_url.rstrip("/"), api_key, max_tokens, timeout
        self.fallback_parses = 0
        self.extra_body = extra_body or {}

    def chat(self, model, messages, tools, temperature=0.0, seed=0):
        body = {"model": model, "messages": messages, "tools": tools, "tool_choice": "auto",
                "temperature": temperature, "max_tokens": self.max_tokens, "seed": seed, **self.extra_body}
        last = None
        for attempt in range(4):
            try:
                r = urllib.request.Request(self.base + "/chat/completions", data=json.dumps(body).encode(),
                                           headers={"Content-Type": "application/json",
                                                    "Authorization": f"Bearer {self.key}"})
                with urllib.request.urlopen(r, timeout=self.timeout) as resp:
                    out = json.loads(resp.read())
                msg = out["choices"][0]["message"]
                if not msg.get("tool_calls"):
                    calls = parse_text_tool_calls(msg.get("content") or "")
                    if calls:
                        self.fallback_parses += 1
                        msg["tool_calls"] = calls
                        msg["_fallback_parsed"] = True
                return msg
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:500]!r}"
                if e.code == 400:   # e.g. context too long: stop the episode
                    raise RuntimeError(last)
            except Exception as e:  # transient
                last = repr(e)
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(last)


_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def parse_text_tool_calls(text: str):
    """Recover tool calls written as text: <tool_call>{...}</tool_call>, or a bare JSON object
    {"name": ..., "arguments"|"parameters": {...}} (Llama-3.1 style)."""
    cands = _TAG.findall(text)
    if not cands:
        t = text.strip()
        t = re.sub(r"^```(?:json)?|```$", "", t).strip()
        if t.startswith("<|python_tag|>"):
            t = t[len("<|python_tag|>"):]
        if t.startswith("{") and t.endswith("}"):
            cands = [t]
    calls = []
    for c in cands:
        try:
            o = json.loads(c)
        except json.JSONDecodeError:
            continue
        name = o.get("name") or o.get("function")
        args = o.get("arguments", o.get("parameters", {}))
        if isinstance(name, str):
            calls.append({"id": "call_" + uuid.uuid4().hex[:8], "type": "function",
                          "function": {"name": name, "arguments": json.dumps(args) if not isinstance(args, str) else args}})
    return calls
