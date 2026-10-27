"""Ranked rollback (plan-tree-search, component 4).

When a branch is declared FAILED (by the orchestrator — e.g. mission not complete and no
progress, or all candidates filtered out, or a depth budget hit), roll back: DFS-backtrack to
the deepest depth with an untried lower-ranked sibling, archive the abandoned tail, re-choose
that sibling, and report the depth to RESUME generating from.

This module only manipulates run.json (no model / no vLLM). Resuming (generating the next
depth from the re-chosen node) is done by run_candidates.py --depth <resume> --run <run.json>.

Usage: python rollback.py <run.json> [failed_depth]   (failed_depth default = deepest step)
"""
import sys
from pathlib import Path
import exputil, runlog


def do_rollback(run_path, failed_depth=None):
    rp = run_path if Path(run_path).is_absolute() else exputil.OUT / run_path
    rl = runlog.RunLog(rp)
    if not rl.data["steps"]:
        print("no steps to roll back")
        return rl, None
    failed_depth = failed_depth if failed_depth is not None else rl.data["steps"][-1]["depth"]
    resume = rl.rollback(failed_depth)
    if resume is None:
        print("tree EXHAUSTED — no untried sibling from depth", failed_depth,
              "up to root; overall FAILURE for this run")
    else:
        k = resume - 1
        st = rl.step(k)
        print(f"rolled back at depth {k}: re-chose c{st['chosen_candidate_id']} "
              f"(tried so far: {st.get('tried_candidate_ids')})")
        print(f"archived subtrees: {len(rl.data['archive'])}")
        print(f"RESUME: generate depth {resume} from the new depth-{k} choice "
              f"(run_candidates.py --depth {resume} --run {Path(rp).name})")
    return rl, resume


if __name__ == "__main__":
    do_rollback(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
