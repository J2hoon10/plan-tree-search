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


def _make_digest(model, run_name, run_path, rl, depth, candidate_id, seed, retry=0):
    """4th phase: distill the just-executed step into a compact digest, store it on the step,
    and append it to the post-hoc analysis log (*.digest.jsonl). `retry` = this depth's BAD_CMD
    fix index (0 = first attempt), so re-executions at the same depth stay distinguishable in the
    log. Best-effort — run_digest.gen already falls back to a code-only digest if the model call
    fails, so this never crashes."""
    digest = run_digest.gen(model, run_name, depth, candidate_id, seed=seed)
    rl.attach_digest(depth, digest)
    p = run_path.parent / (run_path.stem + ".digest.jsonl")
    with open(p, "a") as f:
        f.write(json.dumps({"depth": depth, "retry": retry, "candidate_id": candidate_id, **digest},
                           ensure_ascii=False) + "\n")
    print(f"[iter] d{depth} digest: verdict={digest.get('verdict')}", flush=True)
    return digest


BAD_CMD_RETRY_MAX = 2       # same-depth command fixes before giving up this intent (-> BLOCKED)


def run(model, run_name, max_steps=40, seed=1, temp=0.7, env_exec=None, env_label=None):
    """verdict-driven loop: generate+rank+execute, then branch on the digest verdict —
      RAN_OK   -> advance (depth+1),
      BAD_CMD  -> keep the intent, regenerate ONLY the cmd (fix_command), re-run at this depth,
                  up to BAD_CMD_RETRY_MAX fixes, then escalate to BLOCKED,
      BLOCKED  -> mark the tool dead run-wide and roll back to the next untried plan (sibling->ancestor).
    See docs/verdict_rollback_design.md."""
    env_exec = env_exec or executor.local_env_exec
    run_path = exputil.OUT / run_name
    run_path.parent.mkdir(parents=True, exist_ok=True)
    if run_path.exists():
        run_path.unlink()                      # fresh run
    stem = Path(run_name).stem
    depth, status = 1, "budget_reached"
    method_dead = []        # run-wide: program names proven unavailable (BLOCKED tools)
    history = []            # this depth's BAD_CMD attempts: [{cmd, note}, ...]
    mode, chosen = "GEN", None

    for it in range(1, max_steps + 1):
        if mode == "GEN":
            base = f"{stem}_c_d{depth}_i{it}"
            try:
                obj = run_candidates.gen(model, base, depth=depth,
                                         run=(run_name if depth > 1 else None),
                                         seed=seed, temp=temp, exclude=method_dead or None)
            except Exception as e:      # truncated/unparseable gen -> roll back, don't crash
                print(f"[iter {it}] depth {depth}: gen FAILED ({e}) -> rollback", flush=True)
                rl = runlog.RunLog(run_path)
                resume = rl.rollback(depth - 1) if (depth > 1 and rl.data.get("steps")) else None
                if resume is None:
                    status = "gen_failed"; break
                depth, chosen, history, mode = resume - 1, rl.step(resume - 1)["chosen_candidate_id"], [], "EXEC"
                continue
            print(f"[iter {it}] depth {depth}: {len(obj['next_step_candidates'])} candidates, "
                  f"complete={obj['is_mission_complete']}", flush=True)
            if obj["is_mission_complete"]:
                status = "complete_claimed"; break
            executor.prepare_depth(base + ".json", run_name, depth=depth, env_label=env_label, model=model)
            rl, out = rank_candidates.rank_depth(run_name, model, depth=depth, temp=0.0, seed=seed)
            if out is None:             # nothing selectable here -> roll back
                resume = rl.rollback(depth)
                if resume is None:
                    status = "exhausted"; break
                depth, chosen, history, mode = resume - 1, rl.step(resume - 1)["chosen_candidate_id"], [], "EXEC"
                print(f"[iter {it}] no selectable candidate -> rollback to depth {depth}", flush=True)
                continue
            chosen, history = rl.step(depth)["chosen_candidate_id"], []

        # --- EXEC: run the chosen plan, distill it, branch on the verdict ---
        rl = executor.execute_one(run_name, depth, chosen, env_exec=env_exec)
        digest = _make_digest(model, run_name, run_path, rl, depth, chosen, seed, retry=len(history))
        v = digest.get("verdict")
        st = rl.step(depth)
        print(f"[iter {it}] depth {depth}: executed c{chosen} (order {st.get('ranking_order')}) -> {v}",
              flush=True)
        if rl.data.get("solved"):
            s = rl.data["solved"]
            print(f"[iter {it}] CONNECTED to {s['address']} (c{s['candidate_id']}) at d{s['depth']} "
                  f"-> solved RECORDED (loop continues)", flush=True)

        if v == "RAN_OK":
            depth, mode = depth + 1, "GEN"; continue

        if v == "BAD_CMD":
            cand = rl._cand(depth, chosen)
            history.append({"cmd": cand["cmd"],
                            "note": digest.get("note") or digest.get("observed") or "did not do what was intended"})
            st["fix_attempts"] = history; rl.save()
            if len(history) <= BAD_CMD_RETRY_MAX:        # keep the intent, rewrite only the cmd
                new = run_candidates.fix_command(model, run_name, depth, chosen, history, seed=seed)
                executor.prepare_one(run_name, depth, chosen, new)
                mode = "EXEC"; continue                  # re-run same intent at this depth
            v = "BLOCKED"                                 # out of fixes -> abandon this intent
            d = st["digest"]; d["verdict"] = "BLOCKED"    # record the promotion so run.json matches the loop
            d["note"] = (d.get("note") or "") + f" [promoted from BAD_CMD: unfixable after {BAD_CMD_RETRY_MAX} tries]"
            rl.save()

        if v == "BLOCKED":
            cand = rl._cand(depth, chosen)
            ex = cand.get("exec") or {}
            for m in executor.dead_methods(cand["cmd"], ex.get("stderr", ""), ex.get("rc")):
                if m not in method_dead:
                    method_dead.append(m)
            rl.data["method_dead"] = list(method_dead); rl.save()   # persist for post-hoc analysis
            resume = rl.rollback(depth)
            if resume is None:
                status = "exhausted"; break
            depth, chosen, history, mode = resume - 1, rl.step(resume - 1)["chosen_candidate_id"], [], "EXEC"
            print(f"[iter {it}] BLOCKED (dead tools: {method_dead}) -> rollback to depth {depth}", flush=True)
            continue

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
