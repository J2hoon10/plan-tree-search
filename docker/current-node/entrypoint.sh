#!/bin/sh
# current-node's own boot sequence:
#   1. start vLLM locally (loads THIS container's own weights mount)
#   2. wait for it to answer /health
#   3. hand off to run_agent.py — the agentic loop that decides what to do,
#      running IN THIS SAME container (mini-swe-agent LocalEnvironment)
#   4. once the agent submits/times out, write results to the bind-mounted
#      /out dir and exit — the evaluator watches for this container to exit,
#      then force-removes it (see nodes.py) before touching target-node.
set -e

mkdir -p "$OUT_DIR"

echo "[entrypoint] starting vLLM on :$VLLM_PORT from $WEIGHTS_PATH ..." | tee -a "$OUT_DIR/vllm.log"
# --gpu-memory-utilization is REQUIRED even though --kv-cache-memory-bytes is
# also given — they aren't alternatives. vLLM's startup free-memory check
# gates on `total_mem * utilization` regardless of the KV cache's own size;
# left at vLLM's own default (~0.9 of this host's 119.7GB unified-memory
# pool, i.e. ~110GB) it fails the instant less than that happens to be free,
# independent of how small the actual request is (verified on this host:
# "Free memory ... (105.2/119.7 GiB) ... less than desired GPU memory
# utilization (0.92, 110.12 GiB)" with nothing else of note on the GPU).
# REASONING_PARSER (e.g. "qwen3") is optional and empty by default — unset
# leaves this command byte-for-byte identical to every already-proven
# Instruct-model run. When set, vLLM splits <think>...</think> out of
# message.content into a separate reasoning_content field; harmless even for
# a model that never emits <think> (both Instruct-2507 and Thinking-2507
# register <think>/</think> as special tokens, verified against
# tokenizer_config.json, so this is safe to set per-config, not per-model).
# No --enforce-eager: this used to be hardcoded (paired with
# VLLM_USE_FLASHINFER_SAMPLER=0 to work around a container-only FlashInfer
# JIT/cache blocker, see old plan §19), but --enforce-eager itself was never
# individually verified necessary — it also disables torch.compile/CUDA
# graphs, cutting decode throughput ~2.5-4x (measured: ~3-5 tok/s eager vs
# ~12-13 tok/s compiled, both on this exact host/image, with
# VLLM_USE_FLASHINFER_SAMPLER=0 alone — the actually load-bearing fix —
# kept). --max-num-seqs 1 matches this harness's true concurrency (one
# request at a time) and keeps CUDA-graph-capture startup cost small (~1min
# vs 7+min capturing ~86 unused batch sizes when this flag is omitted).
VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_HOME=/usr/local/cuda \
  "$VLLM_BIN_PY" "$VLLM_BIN" serve "$WEIGHTS_PATH" \
    --port "$VLLM_PORT" --served-model-name "$SERVED_MODEL_NAME" \
    --max-model-len "$MAX_MODEL_LEN" --max-num-seqs 1 \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.3}" \
    --kv-cache-memory-bytes "$KV_CACHE_MEMORY_BYTES" \
    ${REASONING_PARSER:+--reasoning-parser "$REASONING_PARSER"} \
    >> "$OUT_DIR/vllm.log" 2>&1 &
VLLM_PID=$!

echo "[entrypoint] waiting for /health (up to ${HEALTH_WAIT_MIN} min) ..."
i=0
max=$((HEALTH_WAIT_MIN * 4))   # poll every 15s
while [ $i -lt $max ]; do
    if curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$VLLM_PORT/health" 2>/dev/null | grep -q 200; then
        echo "[entrypoint] vLLM healthy after $((i * 15))s"
        break
    fi
    if ! kill -0 "$VLLM_PID" 2>/dev/null; then
        echo "[entrypoint] vLLM process died during startup — see vllm.log" | tee "$OUT_DIR/DONE_ERROR"
        echo '{"exit_status": "VLLM_STARTUP_FAILED", "submission": "", "n_steps": 0}' > "$OUT_DIR/status.json"
        touch "$OUT_DIR/DONE"
        exit 1
    fi
    i=$((i + 1))
    sleep 15
done
if [ $i -ge $max ]; then
    echo "[entrypoint] vLLM never became healthy within ${HEALTH_WAIT_MIN} min" | tee "$OUT_DIR/DONE_ERROR"
    echo '{"exit_status": "VLLM_STARTUP_TIMEOUT", "submission": "", "n_steps": 0}' > "$OUT_DIR/status.json"
    touch "$OUT_DIR/DONE"
    exit 1
fi

echo "[entrypoint] starting local agent loop ..."
python3 /opt/pts/scripts/incontainer_agent.py
echo "[entrypoint] agent loop finished, exiting (evaluator tears this container down next)"
