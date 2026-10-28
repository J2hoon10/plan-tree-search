"""run.json manager for the plan-tree-search tree (single-file log).

Structure:
  {mission, env, model, steps: [depth-record, ...], archive: [...]}
Each depth-record = the model's candidate objects DECORATED in place with `exec`
(after execution) and `rank` (after ranking), plus `chosen_candidate_id`. The path
(parent linkage) is implicit in the order of `steps` — no explicit parent id, per design.
Rollback moves the dropped tail into `archive` (history preserved, still one file).
"""
import json
from pathlib import Path

LOG_MAX = 4000        # chars of RAW stdout/stderr stored per cmd in run.json (for debugging)
STATE_STEP_MAX = 600  # chars of result shown PER STEP in {{STEP_HISTORY}} (context-length control)


def _trunc(s: str, n: int = LOG_MAX) -> str:
    s = s or ""
    return (s[:n] + f" …(+{len(s) - n} chars)") if len(s) > n else s


def _clip(s: str, n: int = STATE_STEP_MAX) -> str:
    """Head+tail clip for {{STEP_HISTORY}} rendering — keeps the start AND end of long output."""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    head = int(n * 0.7)
    return s[:head] + f" …(trimmed {len(s) - n} chars)… " + s[-(n - head):]


class RunLog:
    def __init__(self, path, mission=None, env=None, model=None):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = {"mission": mission, "env": env, "model": model, "steps": [], "archive": []}
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n")

    # --- lookups ---
    def step(self, depth):
        for s in self.data["steps"]:
            if s["depth"] == depth:
                return s
        return None

    def _cand(self, depth, cid):
        for c in self.step(depth)["candidates"]:
            if c["candidate_id"] == cid:
                return c
        raise KeyError((depth, cid))

    # --- mutations (each saves) ---
    def add_step(self, depth, candidates, is_mission_complete=False):
        if self.step(depth) is not None:
            raise ValueError(f"step depth {depth} already exists")
        self.data["steps"].append({
            "depth": depth,
            "candidates": [dict(c) for c in candidates],     # decorate these in place later
            "chosen_candidate_id": None, "is_mission_complete": is_mission_complete})
        self.save()

    def attach_digest(self, depth, digest):
        """Store the post-execution DIGEST for this step: the distilled observation
        (intended/observed/verdict/learned|note) that future STATE renders use in place of
        raw output. One digest per step (for its chosen+executed candidate)."""
        self.step(depth)["digest"] = digest
        self.save()

    def attach_exec(self, depth, candidate_id, *, rc, stdout, stderr, elapsed=None,
                    stderr_axis=None, executable=True, filter_reason="executable"):
        c = self._cand(depth, candidate_id)
        c["exec"] = {"executable": executable, "filter_reason": filter_reason, "rc": rc,
                     "elapsed_s": elapsed, "stderr_axis": stderr_axis,
                     "stdout": _trunc(stdout), "stderr": _trunc(stderr),
                     "stdout_full_len": len(stdout or "")}
        self.save()

    def attach_filter(self, depth, candidate_id, *, ok, reason):
        """Static error-filter result for a candidate PLAN (set before ranking; no execution)."""
        self._cand(depth, candidate_id)["filter"] = {"ok": ok, "reason": reason}
        self.save()

    def attach_rank(self, depth, ranks: dict):     # {candidate_id: rank}
        for cid, rk in ranks.items():
            self._cand(depth, int(cid))["rank"] = rk
        self.save()

    def attach_ranking(self, depth, order, analysis=None, scores=None, judgments=None):
        """order: candidate_ids best->worst. Sets each candidate's rank = position (1-based),
        and (when given) its rank_score (0..5 from _score) and rank_judgment (the model's flags
        for that candidate), so score TIES are directly recoverable from run.json (rank alone
        hides them — it breaks ties by id). Records the model's ranking `analysis` + `order`."""
        for pos, cid in enumerate(order):
            c = self._cand(depth, cid)
            c["rank"] = pos + 1
            if scores is not None and cid in scores:
                c["rank_score"] = scores[cid]
            if judgments is not None and cid in judgments:
                c["rank_judgment"] = judgments[cid]
        st = self.step(depth)
        st["ranking_order"] = order
        if analysis is not None:
            st["ranking_analysis"] = analysis
        self.save()

    def choose(self, depth, candidate_id):
        st = self.step(depth)
        st["chosen_candidate_id"] = candidate_id
        tried = st.setdefault("tried_candidate_ids", [])     # for rollback bookkeeping
        if candidate_id not in tried:
            tried.append(candidate_id)
        self.save()

    def next_untried(self, depth):
        """The next candidate_id in this depth's ranking (best->worst) that has NOT yet been
        chosen/explored. Treats the current chosen_candidate_id as tried even for steps made
        before tried-tracking existed. None if no untried sibling remains."""
        st = self.step(depth)
        tried = set(st.get("tried_candidate_ids", []))
        if st.get("chosen_candidate_id") is not None:
            tried.add(st["chosen_candidate_id"])
        for cid in st.get("ranking_order", []):
            if cid not in tried:
                return cid
        return None

    def rollback(self, failed_depth):
        """DFS backtrack from `failed_depth` toward the root: find the DEEPEST depth that still
        has an untried (lower-ranked) sibling, archive the abandoned tail below it, and re-choose
        that sibling. Returns the depth to RESUME generating (chosen depth + 1), or None if the
        whole tree is exhausted (no untried sibling anywhere)."""
        for k in range(failed_depth, 0, -1):
            nxt = self.next_untried(k)
            if nxt is not None:
                self.rollback_to(k, nxt)       # archives steps>k, chooses nxt (marks tried)
                return k + 1
        return None

    def rollback_to(self, depth, new_chosen_id):
        st = self.step(depth)
        old = st.get("chosen_candidate_id")
        tried = st.setdefault("tried_candidate_ids", [])
        if old is not None and old not in tried:        # preserve the abandoned choice as tried
            tried.append(old)
        keep, drop = [], []
        for s in self.data["steps"]:
            (keep if s["depth"] <= depth else drop).append(s)
        if drop:
            self.data["archive"].append({"rolled_back_at_depth": depth, "dropped": drop})
        self.data["steps"] = keep
        self.choose(depth, new_chosen_id)    # saves (also marks new choice as tried)

    # --- derived views ---
    def chosen_path(self):
        out = []
        for s in sorted(self.data["steps"], key=lambda x: x["depth"]):
            cid = s["chosen_candidate_id"]
            if cid is None:
                break
            out.append((s, self._cand(s["depth"], cid)))
        return out

    def render_state(self, next_depth):
        """{{STEP_HISTORY}} for generating depth `next_depth`: the FULL chosen-path trajectory as a
        cumulative list of per-step DIGESTS (distilled after each step ran). Each prior step
        contributes its digest (intended/observed/verdict + learned|note) instead of raw output,
        so the whole history of what was tried and learned is preserved while staying compact.
        No sliding window, no self-summary re-use. Rollback-safe: re-derived from run.json."""
        path = self.chosen_path()
        lines = [f"depth {next_depth}. Record of prior steps (distilled, oldest first):"]
        if not path:
            lines.append("(no steps taken yet)")
            return "\n".join(lines)

        for s, c in path:
            d = s.get("digest")
            if not d:                      # executed step without a digest (shouldn't happen) -> minimal
                ex = c.get("exec", {})
                lines.append(f"[d{s['depth']}] {c.get('objective', '')} -> rc={ex.get('rc')} (no digest)")
                continue
            line = (f"[d{s['depth']}] intended: {d.get('intended', '')} · "
                    f"verdict: {d.get('verdict', '')}")
            if d.get("finding"):
                line += f"\n      finding: {d['finding']}"
            lines.append(line)
        return "\n".join(lines)
