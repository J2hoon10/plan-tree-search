"""plan-tree-search experiment utilities.

- render(): load this experiment's OWN prompt copies from ../prompts.
- mission(): the task text (../prompts/Task.md).
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"
OUT = Path(os.environ["PTS_OUT"]) if os.environ.get("PTS_OUT") else ROOT / "out"   # in-container: /out


def read(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text().rstrip("\n")


def render(name: str, **kw: str) -> str:
    t = read(name)
    for k, v in kw.items():
        t = t.replace("{{" + k + "}}", str(v))
    return t


def mission() -> str:
    return (PROMPTS / "Task.md").read_text()


ENDPOINT = os.environ.get("PTS_VLLM", "http://127.0.0.1:8000")


def post_chat(model, messages, schema, name, *, temp=0.0, seed=1, max_tokens=2048,
              retries=2, cap=4096):
    """Guided-JSON chat call that is robust to TRUNCATION. With response_format=json_schema
    the output is always grammar-valid unless it was cut off at max_tokens -> json.loads fails.
    On a parse failure we retry with DOUBLED max_tokens (temp unchanged, so the fix is
    deterministic — more room, not a different sample). Returns (obj, raw, finish_reason).
    Raises ValueError if still unparseable after `retries` extra tries."""
    import httpx
    mt, last_err, raw, finish = max_tokens, None, "", None
    for _ in range(retries + 1):
        body = {"model": model, "messages": messages,
                "temperature": temp, "top_p": 1.0 if temp == 0 else 0.8,
                "top_k": -1 if temp == 0 else 20, "seed": seed, "max_tokens": mt,
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}}
        r = httpx.post(f"{ENDPOINT}/v1/chat/completions", json=body, timeout=600.0)
        r.raise_for_status()
        choice = r.json()["choices"][0]
        raw, finish = choice["message"]["content"], choice.get("finish_reason")
        try:
            return json.loads(raw), raw, finish
        except json.JSONDecodeError as e:      # truncated -> grow room and retry
            last_err = e
            mt = min(mt * 2, cap)
    raise ValueError(f"post_chat({name}): unparseable JSON after {retries + 1} tries "
                     f"(finish={finish!r}, len={len(raw)}): {last_err}")
