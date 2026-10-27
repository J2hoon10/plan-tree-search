"""Digest generation (plan-tree-search, component 4): after a step's chosen command runs,
distill its result into a compact per-step record (intended/observed/verdict/learned/note)
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
    "intended": {"type": "string"},
    "observed": {"type": "string"},
    "verdict": {"type": "string", "enum": ["INFO_GAINED", "RAN_BUT_EMPTY", "BAD_CMD", "BLOCKED"]},
    "learned": {"type": "string"},
    "note": {"type": "string"},
  },
  "required": ["intended", "observed", "verdict", "learned", "note"],
}


def _render_step(c):
    """The ONE step just run, rendered as {{STEP}} for the digest prompt."""
    ex = c.get("exec", {})
    out = ex.get("stdout") or ex.get("stderr") or "(no output)"
    return (f"plan: {c.get('objective', '')}\n"
            f"info sought: {c.get('info_to_obtain', '')}\n"
            f"$ {c.get('cmd', '')}\n"
            f"result: rc={ex.get('rc')} elapsed={ex.get('elapsed_s')}s\n"
            f"{runlog._clip(out)}")


def _fallback(c):
    """Code-only digest when the model call fails — verdict inferred from rc alone."""
    ex = c.get("exec", {})
    rc = ex.get("rc")
    out = (ex.get("stdout") or ex.get("stderr") or "").strip()
    if rc in (124, 126, 127):
        verdict, note = "BLOCKED", f"rc={rc}: tool missing or timed out"
    elif rc == 0 and not out:
        verdict, note = "RAN_BUT_EMPTY", "rc=0 with no output"
    else:
        verdict, note = "RAN_BUT_EMPTY", f"rc={rc}; digest model unavailable, raw result kept in run.json"
    return {"intended": c.get("objective", ""),
            "observed": f"rc={rc} elapsed={ex.get('elapsed_s')}s",
            "verdict": verdict, "learned": "", "note": note}


def gen(model, run, depth, candidate_id, seed=1, temp=0.0):
    """Generate the digest for the just-executed (depth, candidate_id). Returns the digest dict."""
    rpath = run if Path(run).is_absolute() else exputil.OUT / run
    c = runlog.RunLog(rpath)._cand(depth, candidate_id)
    msgs = [{"role": "system", "content": exputil.render("plan_system", MISSION=exputil.mission())},
            {"role": "user", "content": exputil.render("plan_user_digest", STEP=_render_step(c))}]
    try:
        obj, _, _ = exputil.post_chat(model, msgs, DIGEST_SCHEMA, "digest",
                                      temp=temp, seed=seed, max_tokens=512)
        return _enforce_blocked_floor(c, obj)
    except Exception as e:  # noqa: BLE001  digest is best-effort; never crash the loop
        print(f"[digest d{depth}] model failed ({e}) -> code fallback", flush=True)
        return _fallback(c)


def _enforce_blocked_floor(c, obj):
    """rc 127/126 (tool missing / not executable) and 124 (timed out) mean the command never
    really ran -> BLOCKED is a fact, not a judgment call. Force it so the model cannot mislabel
    these (test5: ping-not-installed was tagged BAD_CMD). Only this one direction is overridden;
    every other verdict stays the model's call."""
    ex = c.get("exec") or {}
    if isinstance(ex, str):
        try:
            import ast
            ex = ast.literal_eval(ex)
        except Exception:
            ex = {}
    rc = ex.get("rc")
    if rc in (124, 126, 127) and obj.get("verdict") != "BLOCKED":
        obj["verdict"] = "BLOCKED"
        obj["learned"] = ""
        if not obj.get("note"):
            obj["note"] = f"rc={rc}: tool missing or timed out (command did not run)"
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
