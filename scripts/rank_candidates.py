"""Ranking (plan-tree-search, component 2): a free RELATIVE choice — no scoring rubric, no exclude.

The 4B planner reasons poorly with fine-grained criteria, so we do NOT score candidates on any
axis and we do NOT pre-exclude any. The model simply RANKS the filter-passed candidates by free
relative judgment (analysis reasoning FIRST, then the ranking best->worst) — "which is the better
move from here". The best is chosen; the rest stay as rollback siblings.

- Only filter-PASSED candidate PLANS reach the model; execution happens AFTER, on the chosen one.
- If NONE pass the static filter -> no ranking; mark rollback_needed.

Usage: python rank_candidates.py <run.json> <served_model> [depth]   (vLLM must be live on :8000)
"""
import json, sys
from pathlib import Path
import httpx
import exputil, runlog

RANK_SCHEMA = {                       # field order = reasoning BEFORE the decision
  "type": "object", "additionalProperties": False,
  "properties": {
    "ranking_analysis": {"type": "string"},        # reason about the ranking, FIRST
    "ranking": {"type": "array", "minItems": 1, "items": {
      "type": "object", "additionalProperties": False,
      "properties": {"candidate_id": {"type": "integer"}},
      "required": ["candidate_id"]}},
  },
  "required": ["ranking_analysis", "ranking"],
}


def render_candidates(cands):
    """Render the candidate PLANS only — no results, because they have not been run yet
    (ranking precedes execution)."""
    lines = []
    for c in sorted(cands, key=lambda x: x["candidate_id"]):
        lines.append(f"[c{c['candidate_id']}] objective: {c['objective']}\n"
                     f"     info_to_obtain: {c['info_to_obtain']}\n"
                     f"     cmd: {c['cmd']}")
    return "\n".join(lines)


def rank_depth(run_path, model, depth=None, temp=0.0, seed=1):
    run_path = run_path if Path(run_path).is_absolute() else exputil.OUT / run_path
    rl = runlog.RunLog(run_path)
    depth = depth if depth is not None else rl.data["steps"][-1]["depth"]
    step = rl.step(depth)
    cands_ok = [c for c in step["candidates"] if c.get("filter", {}).get("ok")]

    if not cands_ok:
        step["status"] = "rollback_needed"; rl.save()
        print(f"[depth {depth}] no filter-passed candidates -> rollback_needed")
        return rl, None

    msgs = [{"role": "system", "content": exputil.render("plan_system", MISSION=exputil.mission())},
            {"role": "user", "content": exputil.render("rank_candidates",
                 STEP_HISTORY=rl.render_state(depth), CANDIDATES=render_candidates(cands_ok))}]
    try:
        out, _, _ = exputil.post_chat(model, msgs, RANK_SCHEMA, "rank",
                                      temp=temp, seed=seed, max_tokens=2048)
    except Exception as ex:                      # truncation/parse still failing -> don't crash
        step["status"] = "rank_failed"; rl.save()
        print(f"[depth {depth}] ranking failed after retries ({ex}) -> rollback_needed")
        return rl, None

    ok_ids = [c["candidate_id"] for c in cands_ok]
    # the model's free relative order over ALL filter-passed candidates; de-dup and append any
    # the model forgot (by id) so none is silently lost.
    order = []
    for x in out["ranking"]:
        cid = int(x["candidate_id"])
        if cid in ok_ids and cid not in order:
            order.append(cid)
    for cid in ok_ids:
        if cid not in order:
            order.append(cid)

    rl.attach_ranking(depth, order, analysis=out.get("ranking_analysis"))
    rl.choose(depth, order[0])

    print("ranking_analysis:", out.get("ranking_analysis"))
    print("ranking (best->worst):", order, "| chosen:", order[0])
    return rl, out


if __name__ == "__main__":
    rank_depth(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
