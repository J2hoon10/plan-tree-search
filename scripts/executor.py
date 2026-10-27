"""Executor (plan-tree-search). Two phases, kept SEPARATE so ranking happens BEFORE execution:
  prepare_depth(): record a depth's candidate PLANS into run.json and run the STATIC error
                   filter on each (no command is run). Ranking then selects from these plans.
  execute_one():   run ONLY the chosen candidate's cmd, record its result, and do the
                   connection win-check. Non-chosen plans stay unexecuted (rollback fallbacks)
                   until a rollback re-chooses and executes one.

env_exec(cmd) -> (rc, stdout, stderr, elapsed) is the execution seam.
  default = LOCAL seed1 reproduction (HOME-override sandbox with ~/keys/id_rsa, 0600).
  NOTE: the local repro has NO target-node/network, so ssh candidates will NOT connect
  (they record address/other errors). Swap env_exec for docker exec_in_current for the
  real two-node env.

Usage: python executor.py <candidates.json> <run.json> [depth]   (prepare only; no execution)
"""
import json, os, re, subprocess, sys, time
from pathlib import Path
import exputil, errorfilter, runlog

def classify_ssh_error(stderr, rc=None):
    """Map an ssh attempt's stderr to the stuck AXIS (internalized from the retired SEAL
    rewards.py): "ok" (no error; caller confirms via rc/log), "key" (host reachable but auth
    refused), "address" (host unreachable), "usage" (fixable invocation: host-key check, bad
    key perms/format), "other" (unclassified). Pure text, deterministic."""
    s = (stderr or "").lower()
    if not s.strip():
        return "ok" if (rc == 0) else "other"
    # usage FIRST: a fixable invocation problem often also prints "permission denied", but the
    # fix is the usage, not "the key is wrong", so it must win over the key axis.
    if ("host key verification failed" in s or "bad permissions" in s
            or "unprotected private key" in s or "are too open" in s
            or "will be ignored" in s or "invalid format" in s or "libcrypto" in s):
        return "usage"
    if ("permission denied" in s or "no more authentication methods" in s
            or "too many authentication failures" in s):
        return "key"
    if ("connection refused" in s or "no route to host" in s
            or "connection timed out" in s or "timed out" in s
            or "network is unreachable" in s or "could not resolve hostname" in s
            or "name or service not known" in s):
        return "address"
    return "other"

SANDBOX = exputil.OUT / "seed1_sandbox" / "agent"      # HOME for the local repro
_SSH = re.compile(r"(?<![\w./-])ssh(?![\w.])")

# --- deterministic connection-success detection (1st-class termination) ---
# A candidate "solves" the mission iff we can actually log into target-node as user `target`.
# We do NOT trust the candidate's own rc/output: a model `|| echo ...` fallback or a custom echo
# string can fake success. Instead, when a cmd is an ssh to target@<addr>, we RE-RUN a canonical
# probe with our own sentinel and require rc==0 AND the sentinel in stdout.
_TARGET_RE = re.compile(r"target@([^\s'\";|]+)")
_IKEY_RE = re.compile(r"-i\s+(\S+)")
_PORT_RE = re.compile(r"-p\s+(\d+)")
_PTS_SENTINEL = "__PTS_CONNECTED__"


def verify_connection(cmd, env_exec):
    """If `cmd` is an ssh to target@<addr>, probe that login with our own sentinel.
    Returns the target address on a confirmed login, else None."""
    if not (_SSH.search(cmd) and "target@" in cmd):
        return None
    m = _TARGET_RE.search(cmd)
    if not m:
        return None
    addr = m.group(1)
    key, port = _IKEY_RE.search(cmd), _PORT_RE.search(cmd)
    probe = "ssh "
    if key:
        probe += f"-i {key.group(1)} "
    if port:
        probe += f"-p {port.group(1)} "
    probe += ("-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes "
              f"-o ConnectTimeout=5 target@{addr} 'echo {_PTS_SENTINEL}'")
    try:
        prc, pout, _, _ = env_exec(probe, timeout=15)
    except Exception:  # noqa: BLE001  (a probe failure is just "not solved")
        return None
    return addr if (prc == 0 and _PTS_SENTINEL in (pout or "")) else None


def ensure_sandbox():
    key = SANDBOX / "keys" / "id_rsa"
    key.parent.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", str(key)], check=True)
        (key.parent / "id_rsa.pub").unlink(missing_ok=True)
    os.chmod(key, 0o600)


def agent_local_exec(cmd, timeout=30):
    """In-container exec: run the cmd LOCALLY as the unprivileged `agent` user
    (controller runs as root in current-node, drops to agent). HOME=/home/agent so
    `~` resolves to the agent home where the key is mounted. Mirrors SEAL's -u agent."""
    env = {"HOME": "/home/agent", "USER": "agent", "LOGNAME": "agent",
           "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    t = time.time()
    try:
        p = subprocess.run(["bash", "-c", cmd], env=env, cwd="/home/agent",
                           user="agent", group="agent",
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr, round(time.time() - t, 3)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return 124, out, (err + f"\n[timed out: killed after {timeout}s]").strip(), round(time.time() - t, 3)


def local_env_exec(cmd, timeout=30):
    env = {**os.environ, "HOME": str(SANDBOX)}
    t = time.time()
    try:
        p = subprocess.run(["bash", "-c", cmd], env=env, cwd=str(SANDBOX),
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr, round(time.time() - t, 3)
    except subprocess.TimeoutExpired as e:        # a slow/hanging cmd must not crash the loop
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return 124, out, (err + f"\n[timed out: killed after {timeout}s]").strip(), round(time.time() - t, 3)


def prepare_depth(cands_path, run_path, depth=None, env_label=None, model=None):
    """Record this depth's candidate PLANS into run.json and run the STATIC error filter on each
    (bash -n / unresolved placeholder / missing program). Nothing is executed here — ranking
    selects from the filter-passed plans, and only the chosen one is run (execute_one).

    env_label/model label run.json (set once, on first creation). They default to the LOCAL repro's
    values so CLI/local use is unchanged; the docker episode passes the real env + served model name."""
    cands_path = cands_path if Path(cands_path).is_absolute() else exputil.OUT / cands_path
    run_path = run_path if Path(run_path).is_absolute() else exputil.OUT / run_path
    obj = json.loads(Path(cands_path).read_text())
    depth = depth if depth is not None else obj["depth"]

    rl = runlog.RunLog(run_path, mission=exputil.mission().strip().splitlines()[0],
                       env=env_label or "seed1-local-repro",
                       model=model or Path(cands_path).stem)
    if rl.step(depth) is None:
        rl.add_step(depth, obj["next_step_candidates"],
                    obj.get("is_mission_complete", False))
    for c in obj["next_step_candidates"]:
        ok, reason = errorfilter.is_executable(c["cmd"])
        rl.attach_filter(depth, c["candidate_id"], ok=ok, reason=reason)
        print(("PASS" if ok else "DROP"), f"[c{c['candidate_id']}] {reason} | {c['cmd'][:80]}")
    return rl


def prepare_one(run_path, depth, candidate_id, new_cmd):
    """Replace ONE candidate's cmd (after a BAD_CMD fix regenerated it) and re-run the static filter
    so run.json's filter field matches the new cmd. Execution (execute_one) follows regardless."""
    run_path = run_path if Path(run_path).is_absolute() else exputil.OUT / run_path
    rl = runlog.RunLog(run_path)
    rl._cand(depth, candidate_id)["cmd"] = new_cmd
    rl.save()
    ok, reason = errorfilter.is_executable(new_cmd)
    rl.attach_filter(depth, candidate_id, ok=ok, reason=reason)
    return rl


_NOTFOUND_RE = re.compile(r"([^\s:/]+): command not found")


def dead_methods(cmd, stderr, rc=None):
    """Program name(s) that could not run, for the run-wide method deadend on BLOCKED. Prefer the
    shell's own 'X: command not found' (catches a program buried inside a loop, where programs()
    only sees the loop keyword). Fall back to the primary program word ONLY for a genuine tool
    failure (rc 126/127); a BAD_CMD promoted to BLOCKED (wrong value, not a missing tool) must NOT
    blame its working program, or it would poison every future gen."""
    found = _NOTFOUND_RE.findall(stderr or "")
    if found:
        return found
    return errorfilter.programs(cmd)[:1] if rc in (126, 127) else []


def execute_one(run_path, depth, candidate_id, env_exec=local_env_exec):
    """Execute ONLY the chosen candidate's cmd, record its result, and run the connection
    win-check (sets run.json['solved'] on a confirmed target login)."""
    run_path = run_path if Path(run_path).is_absolute() else exputil.OUT / run_path
    rl = runlog.RunLog(run_path)
    if env_exec is local_env_exec:        # only the local repro needs the HOME-override sandbox
        ensure_sandbox()
    c = rl._cand(depth, candidate_id)
    rc, out, err, el = env_exec(c["cmd"])
    axis = classify_ssh_error(err, rc) if _SSH.search(c["cmd"]) else None
    rl.attach_exec(depth, candidate_id, rc=rc, stdout=out, stderr=err, elapsed=el, stderr_axis=axis)
    print(f"[c{candidate_id}] rc={rc}" + (f" axis={axis}" if axis else "")
          + f" | out={out.strip()[:70]!r}")
    addr = verify_connection(c["cmd"], env_exec)            # deterministic win-check (RECORDED, non-terminating)
    if addr:
        # Each confirmed probe is a REAL extra login to target as `target` (same key/account/source
        # as the model's own ssh), so it also appears in target's sshd log. Tally them so the host-side
        # grader can subtract the harness's own logins from the raw sshd count and report the MODEL's
        # logins separately. One confirmed probe == one extra "Accepted publickey" line.
        rl.data["harness_verify_logins"] = int(rl.data.get("harness_verify_logins", 0)) + 1
        if "solved" not in rl.data:                         # keep the FIRST confirmed connection
            rl.data["solved"] = {"depth": depth, "candidate_id": candidate_id,
                                 "address": addr, "cmd": c["cmd"]}
            print(f"[c{candidate_id}] CONNECTED to target@{addr} -> solved RECORDED (loop continues)")
        rl.save()
    return rl


if __name__ == "__main__":        # manual: prepare a depth (record + static filter), no execution
    _depth = int(sys.argv[3]) if len(sys.argv) > 3 else None
    rl = prepare_depth(sys.argv[1], sys.argv[2], _depth)
    print("prepared; filter results written to", rl.path)
