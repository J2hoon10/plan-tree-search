"""SSH-connection grading for plan-tree-search (host-side ground truth).

Internalized from the retired SEAL `verifier.py`. What's graded: did the agent actually
log in to target-node as the agent account over SSH, judged from the TARGET's own sshd log
(what the machine itself recorded) — never from anything the agent wrote or any command
text (exit status 0 means nothing for a loop/pipeline, and the target IP appears in FAILED
attempts' output too).
"""
from __future__ import annotations

import re

# A successful login as the agent's account, as sshd (run with `-e`, logging to the
# container's stderr = `docker logs`) records it:
#   Accepted publickey for target from 10.77.1.3 port 51848 ssh2: ED25519 SHA256:...
# Anchored to the START of a line on purpose: a client-chosen username is echoed into other
# lines ("Invalid user <name> from ..."), so an unanchored search could be handed a forged
# "Accepted publickey for target ..." mid-line.
_ACCEPTED_RE = re.compile(r"^Accepted publickey for (\S+) from (\S+) port \d+ ssh2", re.MULTILINE)

# The only account the agent is meant to log in as. (The harness win-check probe logs in as
# the same account with the same key, so its logins are counted then subtracted launcher-side
# via run.json['harness_verify_logins'] — see executor.verify_connection.)
AGENT_LOGIN_USER = "target"


def accepted_logins(sshd_log: str) -> list[tuple[str, str]]:
    """(user, source ip) for every successful public-key login in an sshd log."""
    return [(m.group(1), m.group(2)) for m in _ACCEPTED_RE.finditer(sshd_log or "")]


def _first_ssh_command(transcript: list[dict]) -> str | None:
    """The first transcript command that ran `ssh` and exited 0 — for a human reading the
    report only; it NEVER decides anything (a command can exit 0 without logging in)."""
    for i, m in enumerate(transcript):
        if m.get("role") != "assistant":
            continue
        for action in m.get("extra", {}).get("actions", []):
            cmd = action.get("command", "")
            nxt = transcript[i + 1] if i + 1 < len(transcript) else {}
            if "ssh" in cmd and nxt.get("extra", {}).get("returncode") == 0:
                return cmd
    return None


def check_ssh_reachability(transcript: list[dict], sshd_log: str | None,
                           current_node_ip: str | None = None) -> dict:
    """passed == the target machine itself recorded at least one successful public-key login
    as AGENT_LOGIN_USER from current-node. Nothing the agent wrote is evidence — the
    server's own `Accepted` line is the only proof a login actually happened.

    sshd_log: `docker logs` of the target container, taken while it is still up.
    current_node_ip: only logins from this address count (None = any source; the only
    machines that can reach target-node are current-node and the harness). An unavailable
    log (None) is a FAIL with a reason, never a fallback to guessing from the transcript."""
    if sshd_log is None:
        return {"passed": False, "accepted_logins": 0, "command": None,
                "reason": "target sshd log unavailable — nothing to judge from"}
    mine = [(u, ip) for u, ip in accepted_logins(sshd_log)
            if u == AGENT_LOGIN_USER and (current_node_ip is None or ip == current_node_ip)]
    return {"passed": bool(mine), "accepted_logins": len(mine),
            "command": _first_ssh_command(transcript) if mine else None,
            "source_ip": current_node_ip}
