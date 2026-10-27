"""Container/node lifecycle primitives for plan-tree-search (docker CLI via subprocess).

Internalized from the retired SEAL `nodes.py` — ONLY the functions the exp2 launcher's
build path actually uses: create/remove network, start target-node (+ wait for sshd),
docker exec, container logs, container IP, force-remove. No SEAL dependency; no `docker`
SDK (rootless daemon on this host, driven through the `docker` CLI).
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

# exp2 slim images (built by run_exp2._ensure_exp2_images). These are the defaults;
# run_exp2 may re-point them at runtime, but they already name the exp2 images.
CURRENT_IMAGE = "pts-exp2-current-node:latest"
TARGET_IMAGE = "pts-exp2-target-node:latest"


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


# ---------------------------------------------------------------- network ---

def create_network(run_id: str, subnet: str | None = None) -> str:
    """A dedicated internal bridge for one episode. `subnet` is a small explicit CIDR
    (e.g. 10.77.1.0/28) so a full-subnet scan from current-node is tractable — docker's
    default auto-subnet is a /16 (65k+ addrs), which would make "scan your subnet" an
    hours-long brute force unrelated to the capability tested."""
    name = f"pts-{run_id}"
    if _run(["docker", "network", "inspect", name]).returncode != 0:
        cmd = ["docker", "network", "create", "--internal"]
        if subnet:
            cmd += ["--subnet", subnet]
        cmd.append(name)
        r = _run(cmd)
        if r.returncode != 0:
            raise RuntimeError(f"network create failed: {r.stderr}")
    return name


def remove_network(name: str) -> None:
    _run(["docker", "network", "rm", name])


def get_container_ip(container: str, network: str) -> str:
    """target-node's real IP on the shared bridge, host-side ground truth via
    `docker inspect`. Uses the Go template `index` (not `.Networks.<name>` dot-access):
    network names are `pts-<run_id>` and run_id always has hyphens, which Go's
    template lexer rejects in a dotted key selector ("bad character U+002D '-'"); `index`
    takes the key as a quoted string and sidesteps the lexer entirely."""
    r = _run(["docker", "inspect", "-f",
              f'{{{{(index .NetworkSettings.Networks "{network}").IPAddress}}}}', container])
    ip = r.stdout.strip()
    if r.returncode != 0 or not ip:
        raise RuntimeError(f"could not determine IP of {container} on {network}: {r.stderr}")
    return ip


def container_logs(container: str) -> str | None:
    """Everything the container wrote to stdout+stderr (`docker logs`), or None if docker
    can't give it. target-node's sshd runs with `-e`, so its log (every login accepted or
    refused) is the container's stderr — the one record of who actually logged in."""
    r = _run(["docker", "logs", container])
    if r.returncode != 0:
        return None
    return (r.stdout or "") + (r.stderr or "")


# ----------------------------------------------------------- docker exec ---

def docker_exec(container: str, command: str, user: str | None = None,
                stdin: str | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec"]
    if stdin is not None:
        cmd.append("-i")
    if user:
        cmd += ["-u", user]
    cmd += [container, "sh", "-c", command]
    # errors="replace": a command may emit non-UTF-8 bytes; decoding must not crash.
    return subprocess.run(cmd, capture_output=True, input=stdin, timeout=timeout,
                          encoding="utf-8", errors="replace")


# ------------------------------------------------------------- target node ---

def start_target_node(run_id: str, network: str, home_dir: Path,
                      authorized_key: str,
                      network_alias: str | None = "target-host",
                      static_ip: str | None = None) -> str:
    """Empty target-destination machine: entrypoint only starts sshd + injects the
    authorized key (no GPU/CUDA — target never runs inference).

    network_alias=None: no DNS name registered, so current-node gets only target's bare
    IP on the shared bridge (no shortcut past a real lookup/scan).
    static_ip: pin target to a specific address (target is the first container on a fresh
    network, so without this every run lands on the same auto-assigned addr). current-node,
    started afterwards with no --ip, is unaffected — docker IPAM skips the taken address."""
    name = f"target-{run_id}"
    home_dir.mkdir(parents=True, exist_ok=True)
    _run(["docker", "rm", "-f", name])
    cmd = ["docker", "run", "-d", "--name", name, "--network", network]
    if network_alias:
        cmd += ["--network-alias", network_alias]
    if static_ip:
        cmd += ["--ip", static_ip]
    cmd += [
        "-e", f"TARGET_AUTHORIZED_KEY={authorized_key}",
        "-v", f"{home_dir}:/home/target",
        "--memory", "20g",
        TARGET_IMAGE,
    ]
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"target-node start failed: {r.stderr}")
    _wait_ssh(name)
    return name


def _wait_ssh(container: str, timeout_s: int = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = docker_exec(container, "ss -tln 2>/dev/null | grep -q ':22' && echo up || echo no")
        if "up" in r.stdout:
            return
        time.sleep(1)
    raise TimeoutError(f"sshd on {container} not listening within {timeout_s}s")


# --------------------------------------------------------- blocking teardown ---

def force_remove_and_confirm(container: str) -> bool:
    """Blocking `docker rm -f` + confirm the container is actually gone. Never rely on
    anything inside the container to clean itself up."""
    _run(["docker", "rm", "-f", container])
    for _ in range(20):
        if _run(["docker", "inspect", container]).returncode != 0:
            return True
        time.sleep(0.5)
    return False
