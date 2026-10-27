#!/usr/bin/env python3
"""In-container tree-search controller (plan-tree-search, experiment 2).

Run as /opt/pts/scripts/incontainer_agent.py (the mounted scripts dir). The current-node
entrypoint starts vLLM on 127.0.0.1:$VLLM_PORT, waits for /health, then runs THIS. It runs the full tree
search IN this container: generate candidates -> filter -> execute (as the
unprivileged `agent`) -> rank -> choose / rollback, writing run.json + per-iter
files to /out (bind-mounted to the host for live logs).

Host code (loop/executor/rank/runlog/run_candidates/exputil) is mounted at
/opt/pts; prompts at /opt/pts/prompts. Model endpoint = 127.0.0.1:8000 (VLLM_PORT=8000).
"""
import os, sys, json, traceback

sys.path.insert(0, "/opt/pts/scripts")
os.environ.setdefault("PTS_OUT", os.environ.get("OUT_DIR", "/out"))

import loop, executor                       # noqa: E402  (after sys.path/env setup)

OUT = os.environ["PTS_OUT"]
os.makedirs(OUT, exist_ok=True)
model = os.environ.get("SERVED_MODEL_NAME", "qwen3-4b")
max_steps = int(os.environ.get("PTS_MAX_STEPS", "40"))

run_label = os.environ.get("PTS_RUN_LABEL")        # host-side run identity (series/seed/tier); None in local repro
print(f"[incontainer_agent] model={model} max_steps={max_steps} OUT={OUT} label={run_label}", flush=True)
try:
    status, depth = loop.run(model, "run.json", max_steps=max_steps, seed=1, temp=0.7,
                             env_exec=executor.agent_local_exec, env_label=run_label)
    with open(os.path.join(OUT, "status.json"), "w") as f:
        json.dump({"exit_status": status, "reached_depth": depth}, f)
except Exception:
    traceback.print_exc()
    with open(os.path.join(OUT, "status.json"), "w") as f:
        json.dump({"exit_status": "ERROR"}, f)
finally:
    with open(os.path.join(OUT, "DONE"), "w") as f:
        f.write("done\n")
    print("[incontainer_agent] DONE", flush=True)
