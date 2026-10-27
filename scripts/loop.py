"""Orchestrator loop (plan-tree-search): rank BEFORE executing, then run only the chosen plan.

Per iteration at the current depth:
  1. generate candidate next-step PLANS (run_candidates.gen) with STATE = chosen-path trajectory,
  2. record the plans + run the STATIC error filter (executor.prepare_depth) — nothing is run yet,
  3. rank the filter-passed plans from the trajectory alone and choose the best
     (rank_candidates.rank_depth); the non-chosen plans stay as rollback fallbacks,
  4. execute ONLY the chosen plan (executor.execute_one); its result feeds the next depth,
  5. a deterministic CONNECTION is RECORDED in run.json['solved'] but does NOT stop the loop — the
     model keeps running so we can observe whether it recognizes success; the loop stops only on the
     model's is_mission_complete claim, budget, or exhaustion. Roll back if nothing is selectable.

run(...) is importable (the in-container controller calls it with env_exec=agent_local_exec).
CLI: python loop.py MODEL RUN_NAME [--max-steps N] [--seed S] [--temp T]
"""
import argparse, json
from pathlib import Path
import exputil, rank_candidates, run_candidates, run_digest, executor, runlog


def _make_digest(model, run_name, run_path, rl, depth, candidate_id, seed):
    """4th phase: distill the just-executed step into a compact digest, store it on the step,
    and append it to the post-hoc analysis log (*.digest.jsonl). Best-effort — run_digest.gen
    already falls back to a code-only digest if the model call fails, so this never crashes."""
    digest = run_digest.gen(model, run_name, depth, candidate_id, seed=seed)
    rl.attach_digest(depth, digest)
    p = run_path.parent / (run_path.stem + ".digest.jsonl")
    with open(p, "a") as f:
        f.write(json.dumps({"depth": depth, "candidate_id": candidate_id, **digest},
                           ensure_ascii=False) + "\n")
    print(f"[iter] d{depth} digest: verdict={digest.get('verdict')}", flush=True)


def run(model, run_name, max_steps=40, seed=1, temp=0.7, env_exec=None, env_label=None):
    env_exec = env_exec or executor.local_env_exec
    run_path = exputil.OUT / run_name
    run_path.parent.mkdir(parents=True, exist_ok=True)
    if run_path.exists():
        run_path.unlink()                      # fresh run
    stem = Path(run_name).stem
    depth, status = 1, "budget_reached"

    for it in range(1, max_steps + 1):
        base = f"{stem}_c_d{depth}_i{it}"
        # 1. generate candidate next-step PLANS from the chosen-path trajectory
        try:
            obj = run_candidates.gen(model, base, depth=depth,
                                     run=(run_name if depth > 1 else None), seed=seed, temp=temp)
        except Exception as e:          # gen failed (e.g. truncated/unparseable JSON) -> roll back, don't crash
            print(f"[iter {it}] depth {depth}: gen FAILED ({e}) -> rollback", flush=True)
            rl = runlog.RunLog(run_path)
            resume = rl.rollback(depth - 1) if (depth > 1 and rl.data.get("steps")) else None
            if resume is None:
                status = "gen_failed"; break
            depth = resume - 1
            chosen = rl.step(depth)["chosen_candidate_id"]
            rl = executor.execute_one(run_name, depth, chosen, env_exec=env_exec)
            _make_digest(model, run_name, run_path, rl, depth, chosen, seed)
            if rl.data.get("solved"):
                s = rl.data["solved"]
                print(f"[iter {it}] CONNECTED to {s['address']} (c{s['candidate_id']}) -> solved RECORDED "
                      f"(not terminating)", flush=True)
            depth += 1
            continue
        print(f"[iter {it}] depth {depth}: {len(obj['next_step_candidates'])} candidates, "
              f"complete={obj['is_mission_complete']}", flush=True)
        if obj["is_mission_complete"]:
            status = "complete_claimed"; break

        # 2. record plans + STATIC filter (no execution), then 3. rank/select the next step
        executor.prepare_depth(base + ".json", run_name, depth=depth, env_label=env_label, model=model)
        rl, out = rank_candidates.rank_depth(run_name, model, depth=depth, temp=0.0, seed=seed)

        if out is None:                         # nothing selectable here -> roll back
            resume = rl.rollback(depth)
            if resume is None:
                status = "exhausted"; break
            depth = resume - 1                  # a lower-ranked sibling was re-chosen at this depth
            print(f"[iter {it}] rollback -> re-chose at depth {depth} (resume {resume})", flush=True)

        # 4. execute ONLY the chosen plan; its result feeds the next depth's trajectory
        chosen = rl.step(depth)["chosen_candidate_id"]
        rl = executor.execute_one(run_name, depth, chosen, env_exec=env_exec)
        # 5. distill the executed step into a digest (future STATE uses this, not raw output)
        _make_digest(model, run_name, run_path, rl, depth, chosen, seed)
        st = rl.step(depth)
        print(f"[iter {it}] depth {depth}: executed c{chosen} (order {st.get('ranking_order')})",
              flush=True)
        if rl.data.get("solved"):               # connection RECORDED (run.json['solved']); loop CONTINUES
            s = rl.data["solved"]
            print(f"[iter {it}] CONNECTED to {s['address']} (c{s['candidate_id']}) -> solved RECORDED "
                  f"at d{s['depth']} (not terminating; model keeps running)", flush=True)
        depth += 1

    _sv = runlog.RunLog(run_path).data.get("solved")
    print(f"LOOP END: status={status}, reached depth {depth}, "
          f"solved={('at d' + str(_sv['depth'])) if _sv else 'none'}, run={run_path}", flush=True)
    return status, depth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model"); ap.add_argument("run_name")
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--temp", type=float, default=0.7)
    a = ap.parse_args()
    run(a.model, a.run_name, max_steps=a.max_steps, seed=a.seed, temp=a.temp)


if __name__ == "__main__":
    main()
