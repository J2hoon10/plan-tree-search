"""Error filter (plan-tree-search) — STATIC executability check of a candidate's cmd.

Judges ONLY "is this a runnable command?", NOT whether it makes progress or errors
semantically. A cmd FAILS iff:
  (1) it contains an unresolved placeholder like <address> / <path-to-key>, OR
  (2) it is not valid shell syntax (bash -n), OR
  (3) a program it invokes does not exist in the execution environment (command -v).

NOT failure conditions (these PASS the filter by design):
  - pipes (|) / chaining (&&, ||, ;)  -> executable; prompt-rule violations handled elsewhere.
  - ssh to a wrong host               -> executable; its rc/error is a later reward signal.
  - a command that returns empty / rc!=0 at runtime -> we don't run it here, so not judged.

The checks run via `rc_fn(check_cmd)->rc` in the EXECUTION ENV. Default = local bash;
swap for a docker-exec callable to check INSIDE current-node (program availability differs).

Usage: python errorfilter.py <candidates.json>   (reads ../out, writes <stem>_filter.json)
Only stdlib; no vLLM, no SEAL import needed.
"""
import json, re, shlex, subprocess, sys
from pathlib import Path
import exputil

PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9 _.\-/]*>")   # <address>, <path-to-key>, ...


def local_rc(check_cmd: str) -> int:
    return subprocess.run(["bash", "-c", check_cmd], capture_output=True).returncode


REDIR = re.compile(r"^\d*[<>]")   # 2>/dev/null, >out, <in, 2>&1 ...


def programs(cmd: str):
    """Program word of each top-level segment, tokenized quote/escape-aware (shlex) so
    that | && ; inside `grep -E '...'` regexes or find's `\\;` are NOT split as operators.
    Skips leading VAR=val / sudo / cd / redirections, plus any `-exec <prog>`."""
    try:
        words = shlex.split(cmd)      # respects quotes & backslash escapes
    except ValueError:
        return []                     # unbalanced quotes -> bash -n already judged it
    out, seg, segs = [], [], []
    for t in words + ["|"]:           # trailing sentinel flushes the last segment
        if t in ("|", "||", "&&", ";", "&"):
            segs.append(seg); seg = []
        else:
            seg.append(t)
    for toks in segs:
        i = 0
        while i < len(toks) and (re.match(r"^[A-Za-z_]\w*=", toks[i]) or toks[i] in ("sudo",)):
            i += 1
        if i < len(toks) and toks[i] == "cd":          # `cd path && ...` already split on &&
            i += 2
        while i < len(toks) and REDIR.match(toks[i]):  # skip leading redirections
            i += 1
        if i < len(toks) and not toks[i].startswith("-"):
            out.append(toks[i])
        if "-exec" in toks:
            j = toks.index("-exec")
            if j + 1 < len(toks) and not toks[j + 1].startswith("-"):
                out.append(toks[j + 1])
    return [p for p in out if p and not REDIR.match(p)]


def is_executable(cmd: str, rc_fn=local_rc):
    m = PLACEHOLDER.search(cmd)
    if m:
        return False, f"unresolved placeholder {m.group(0)}"
    if rc_fn("bash -n -c " + shlex.quote(cmd)) != 0:
        return False, "shell syntax error"
    for p in programs(cmd):
        if rc_fn("command -v " + shlex.quote(p) + " >/dev/null 2>&1") != 0:
            return False, f"command not found: {p}"
    return True, "executable"


def _cmds_of(obj):
    """Yield (candidate_id, cmd) from a candidates file or a whole-plan file."""
    if "next_step_candidates" in obj:
        for c in obj["next_step_candidates"]:
            yield c["candidate_id"], c["cmd"]
    elif "plan" in obj:
        for s in obj["plan"]:
            for i, c in enumerate(s["cmds"], 1):
                yield f"s{s['stage']}.{i}", c


if __name__ == "__main__":
    path = Path(sys.argv[1])
    if not path.is_absolute():
        path = exputil.OUT / path
    obj = json.loads(path.read_text())
    rows = []
    for cid, cmd in _cmds_of(obj):
        ok, reason = is_executable(cmd)
        rows.append({"candidate_id": cid, "cmd": cmd, "executable": ok, "reason": reason})
        print(("PASS" if ok else "DROP"), f"[{cid}]", reason, "|", cmd[:90])
    outp = exputil.OUT / (path.stem + "_filter.json")
    outp.write_text(json.dumps({"source": path.name, "results": rows}, indent=2, ensure_ascii=False) + "\n")
    print("wrote", outp)
