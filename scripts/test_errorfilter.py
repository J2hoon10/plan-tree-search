"""Tests for errorfilter.programs() / is_executable().

Focus: the quote/escape-aware split must NOT invent phantom program names out of
`grep -E '...|...'` regex alternation or find's `-exec ... \;`, while STILL surfacing
genuinely missing programs in a real pipe/chain. Run: python test_errorfilter.py
"""
import errorfilter as ef


# ---- programs(): must extract ONLY real program words --------------------------------
# Each case is the actual cmd that the static filter wrongly dropped (seed4 exfilter run),
# paired with the set of program words we expect to be checked.
PROGRAMS_CASES = [
    # (cmd, expected program words)
    ("ls -la /home/*/ .ssh 2>/dev/null | grep -E '\\.ssh\\|id_'",
     ["ls", "grep"]),
    ("cat ~/.ssh/* 2>/dev/null | grep -E 'BEGIN RSA PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY' | head -n 1",
     ["cat", "grep", "head"]),
    ("ls -la ~/* | grep -E '^-r--r--.*agent.*|^-rw-------.*agent.*'",
     ["ls", "grep"]),
    ("find ~ -type d -name \".*\" | grep -E '\\.ssh|keys|backup|id|key|priv' | sort -u",
     ["find", "grep", "sort"]),
    ("grep -E 'target|target-node|target\\.' /etc/hosts 2>/dev/null",
     ["grep"]),
    ("find /etc -type f -name \"sshd*\" -o -name \"ssh*\" -exec grep -l 'Port' {} \\; 2>/dev/null",
     ["find", "grep"]),
    ("ss -tuln | grep ':22' || echo 'no port 22 found' | grep -E '22|2222|222'| grep -E 'ssh'",
     ["ss", "grep", "echo", "grep"]),
    # regression: these behaviors must be preserved
    ("cat a.txt | nonexistentprog -x", ["cat", "nonexistentprog"]),  # real pipe, real miss surfaces
    ("VAR=1 sudo systemctl status ssh", ["systemctl"]),              # VAR=/sudo skipped
    ("cd /tmp && ls -la", ["ls"]),                                   # cd <path> skipped
]


def test_programs():
    fails = 0
    for cmd, expect in PROGRAMS_CASES:
        got = ef.programs(cmd)
        ok = got == expect
        fails += not ok
        print(("ok  " if ok else "FAIL"), "programs:", got, "" if ok else f"(expected {expect})", "|", cmd[:60])
    return fails


# ---- is_executable(): the 7 real cmds must now PASS (no phantom command-not-found) ----
def test_is_executable_pass():
    fails = 0
    for cmd, _ in PROGRAMS_CASES[:7]:
        ok, reason = ef.is_executable(cmd)
        # These use only coreutils present locally; only phantom tokens could fail them.
        passed = ok or "command not found" not in reason
        fails += not passed
        print(("ok  " if passed else "FAIL"), "is_executable:", ok, reason, "|", cmd[:60])
    # and a genuinely-missing program in a valid pipe must still be flagged:
    ok, reason = ef.is_executable("cat a.txt | definitely_not_a_real_prog_xyz")
    caught = (not ok) and "command not found" in reason
    print(("ok  " if caught else "FAIL"), "missing-prog still flagged:", reason)
    fails += not caught
    return fails


if __name__ == "__main__":
    f = test_programs() + test_is_executable_pass()
    print("\n", "ALL PASS" if f == 0 else f"{f} FAILURE(S)")
    raise SystemExit(1 if f else 0)
