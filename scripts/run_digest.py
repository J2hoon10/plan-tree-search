"""Digest generation (plan-tree-search, component 4): after a step's chosen command runs,
distill its result into a compact per-step record (verdict + finding)
that future STATE renders use in PLACE of raw output. Input = the ONE step just run.

verdict is an enum; a model/parse failure falls back to a code-only digest (verdict inferred
from rc) so the loop never crashes. Call: gen(model, run, depth, candidate_id).
"""
import argparse
from pathlib import Path
import httpx  # noqa: F401  (used via exputil.post_chat)
import exputil, runlog

DIGEST_SCHEMA = {
  "type": "object", "additionalProperties": False,
  "properties": {
    "verdict": {"type": "string", "enum": ["RAN_OK", "BAD_CMD", "BLOCKED"]},
    "finding": {"type": "string"},
  },
  "required": ["verdict", "finding"],
}
# `intended` is NOT a model field: gen() sets it to the step's objective after the call.


def _render_step(c):
    """The ONE step just run, rendered as {{STEP}} for the digest prompt."""
    ex = c.get("exec", {})
    parts = [f"[{k}]\n{ex[k]}" for k in ("stdout", "stderr") if (ex.get(k) or "").strip()]
    out = "\n".join(parts) or "(no output)"
    return (f"objective: {c.get('objective', '')}\n"
            f"info_to_obtain: {c.get('info_to_obtain', '')}\n"
            f"$ {c.get('cmd', '')}\n"
            f"exec: rc={ex.get('rc')} elapsed={ex.get('elapsed_s')}s\n"
            f"{out}")


def _fallback(c):
    """Code-only digest when the model call fails — verdict inferred from rc alone. `intended` is
    added by gen() (= the step's objective), so it is not set here."""
    ex = c.get("exec", {})
    rc = ex.get("rc")
    if rc in (126, 127):
        verdict, finding = "BLOCKED", f"rc={rc}: program missing or not executable"
    elif rc == 124:
        verdict, finding = "BAD_CMD", ""           # BAD_CMD records no finding
    else:
        verdict, finding = "RAN_OK", f"rc={rc}; digest model unavailable, raw result in run.json"
    return {"verdict": verdict, "finding": finding}


def gen(model, run, depth, candidate_id, seed=1, temp=0.0):
    """Generate the digest for the just-executed (depth, candidate_id). Returns the digest dict."""
    rpath = run if Path(run).is_absolute() else exputil.OUT / run
    c = runlog.RunLog(rpath)._cand(depth, candidate_id)
    msgs = [{"role": "system", "content": exputil.render("plan_system", MISSION=exputil.mission())},
            {"role": "user", "content": exputil.render("plan_user_digest", STEP=_render_step(c))}]
    try:
        obj, _, _ = exputil.post_chat(model, msgs, DIGEST_SCHEMA, "digest",
                                      temp=temp, seed=seed, max_tokens=512)
        obj = _enforce_rc_floor(c, obj)
    except Exception as e:  # noqa: BLE001  digest is best-effort; never crash the loop
        print(f"[digest d{depth}] model failed ({e}) -> code fallback", flush=True)
        obj = _fallback(c)
    obj["intended"] = c.get("objective", "")        # intended = the step's objective (not model-generated)
    return obj


def _enforce_rc_floor(c, obj):
    """rc 126/127 (program missing / not executable) => BLOCKED, and rc 124 (timed out) => BAD_CMD
    are FACTS, not judgment calls — force them so the model can't mislabel (test5: ping-not-installed
    was tagged BAD_CMD). 124 is BAD_CMD not BLOCKED on purpose: a timeout means the command was too
    slow (shrink it), NOT that the tool is unavailable, so it must not kill the whole method. Every
    other verdict stays the model's call."""
    ex = c.get("exec") or {}
    if isinstance(ex, str):
        try:
            import ast
            ex = ast.literal_eval(ex)
        except Exception:
            ex = {}
    rc = ex.get("rc")
    if rc in (126, 127) and obj.get("verdict") != "BLOCKED":
        obj["verdict"] = "BLOCKED"                  # tool unusable -> finding records which tool
        obj["finding"] = obj.get("finding") or f"rc={rc}: program missing or not executable"
    elif rc == 124 and obj.get("verdict") != "BAD_CMD":
        obj["verdict"] = "BAD_CMD"                  # too slow -> command rewritten, no finding
        obj["finding"] = ""
    return obj


if __name__ == "__main__":
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("model"); ap.add_argument("run")
    ap.add_argument("--depth", type=int, required=True)
    ap.add_argument("--candidate-id", type=int, required=True)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    print(json.dumps(gen(a.model, a.run, a.depth, a.candidate_id, seed=a.seed),
                     indent=2, ensure_ascii=False))
