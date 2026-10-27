"""Candidate generation (plan_tree_search).
  system = plan_system (+MISSION), user = plan_user_candidates (+STATE).
STATE:
  depth 1      -> fixed initial state (nothing observed yet)
  depth > 1    -> runlog.render_state(depth) from --run <run.json> (the chosen-path trajectory)

Usage:
  python run_candidates.py MODEL OUT_BASENAME [--depth N] [--run run.json] [--seed S] [--temp T]
Writes OUT_BASENAME.json/.raw.txt to ../out. Needs httpx + a vLLM server on :8000.
"""
import argparse, json
from pathlib import Path
import httpx
import exputil, runlog

CANDIDATES_SCHEMA = {
  "type": "object", "additionalProperties": False,
  "properties": {
    "depth": {"type": "integer"},
    "is_mission_complete": {"type": "boolean"},
    "next_step_candidates": {"type": "array", "minItems": 0, "maxItems": 3, "items": {
      "type": "object", "additionalProperties": False,
      "properties": {
        "candidate_id": {"type": "integer"},
        "precondition": {"type": "string"},
        "objective": {"type": "string"},
        "info_to_obtain": {"type": "string"},
        "cmd": {"type": "string"}},
      "required": ["candidate_id", "precondition", "objective", "info_to_obtain", "cmd"]}},
  },
  "required": ["depth", "is_mission_complete", "next_step_candidates"],
}

INITIAL_STATE = ("depth 1 — the mission has just started. No command has been executed yet; nothing "
                 "about current-node or target-node has been observed.")

FIX_SCHEMA = {
  "type": "object", "additionalProperties": False,
  "properties": {"change": {"type": "string"}, "cmd": {"type": "string"}},
  "required": ["change", "cmd"],
}


def _render_history(history):
    """(cmd, note) attempts for {{HISTORY}} in the command-fix prompt, oldest -> newest."""
    return "\n".join(f"  {i}. $ {h['cmd']}\n     -> wrong: {h.get('note') or '(no detail)'}"
                     for i, h in enumerate(history, 1))


def fix_command(model, run, depth, candidate_id, history, seed=1, temp=0.0):
    """BAD_CMD recovery: keep the chosen candidate's INTENT (objective/info/precondition), regenerate
    ONLY its `cmd`. `history` = [{cmd, note}, ...] already tried at this depth, so the fix differs
    from all of them. Returns the corrected cmd string."""
    rpath = run if Path(run).is_absolute() else exputil.OUT / run
    c = runlog.RunLog(rpath)._cand(depth, candidate_id)
    msgs = [{"role": "system", "content": exputil.render("plan_system", MISSION=exputil.mission())},
            {"role": "user", "content": exputil.render("plan_user_cmdfix",
                 OBJECTIVE=c.get("objective", ""), INFO=c.get("info_to_obtain", ""),
                 PRECONDITION=c.get("precondition", ""), HISTORY=_render_history(history))}]
    obj, _, _ = exputil.post_chat(model, msgs, FIX_SCHEMA, "cmdfix", temp=temp, seed=seed, max_tokens=512)
    return obj["cmd"]


def gen(model, out_basename, depth=1, run=None, seed=1, temp=0.7, exclude=None):  # Qwen rec: 0.7/top_p0.8/top_k20
    if depth > 1:
        if not run:
            raise SystemExit("--run <run.json> is required for depth > 1")
        rpath = run if Path(run).is_absolute() else exputil.OUT / run
        state = runlog.RunLog(rpath).render_state(depth)
    else:
        state = INITIAL_STATE
    if exclude:        # programs proven unavailable/blocked in this environment -> never propose them
        state += ("\n\nUNAVAILABLE in this environment (do NOT propose any command using these "
                  "programs — they are missing or cannot run): " + ", ".join(exclude))

    msgs = [{"role": "system", "content": exputil.render("plan_system", MISSION=exputil.mission())},
            {"role": "user", "content": exputil.render("plan_user_candidates", STATE=state)}]
    obj, raw, finish = exputil.post_chat(model, msgs, CANDIDATES_SCHEMA, "cand",
                                         temp=temp, seed=seed, max_tokens=2048)

    exputil.OUT.mkdir(parents=True, exist_ok=True)
    (exputil.OUT / f"{out_basename}.raw.txt").write_text(raw)
    obj = json.loads(raw)
    (exputil.OUT / f"{out_basename}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    print(f"model={model} depth={depth} temp={temp} seed={seed} finish={finish} "
          f"candidates={len(obj['next_step_candidates'])} complete={obj['is_mission_complete']}")
    print("STATE used:\n" + state)
    print("=" * 70)
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    return obj


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("model"); ap.add_argument("out_basename")
    ap.add_argument("--depth", type=int, default=1); ap.add_argument("--run", default=None)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--temp", type=float, default=0.7)
    a = ap.parse_args()
    gen(a.model, a.out_basename, depth=a.depth, run=a.run, seed=a.seed, temp=a.temp)
