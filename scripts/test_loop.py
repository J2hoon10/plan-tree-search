"""Mock unit test for loop.run's verdict-driven branching — NO vLLM / NO docker.

Only the network seam (exputil.post_chat) and the execution seam (env_exec) are faked; loop,
runlog, rollback, executor.execute_one/prepare_one/prepare_depth/dead_methods and _enforce_rc_floor
all run for real. One scripted episode exercises every branch:

  d1 c1  RAN_OK                      -> advance
  d2 c1  BAD_CMD x3 (2 fixes)        -> escalate to BLOCKED (must NOT mark a tool dead)
         rollback to sibling c2  RAN_OK -> advance
  d3 c1  rc127 (ping missing)        -> real BLOCKED, method_dead = ['ping']
         rollback to sibling c2  RAN_OK -> advance
  d4     is_mission_complete         -> stop

Run: python scripts/test_loop.py
"""
import json, os, sys, tempfile, types
from pathlib import Path

sys.modules.setdefault("httpx", types.ModuleType("httpx"))     # loop's deps import httpx at module load
os.environ["PTS_OUT"] = tempfile.mkdtemp(prefix="pts_test_")    # keep the real out/ clean
sys.path.insert(0, str(Path(__file__).resolve().parent))
import exputil, loop  # noqa: E402

CANDS = [
    {"depth": 1, "is_mission_complete": False, "next_step_candidates": [
        {"candidate_id": 1, "objective": "o1", "info_to_obtain": "i", "cmd": "echo d1c1"},
        {"candidate_id": 2, "objective": "o1b", "info_to_obtain": "i", "cmd": "echo d1c2"}]},
    {"depth": 2, "is_mission_complete": False, "next_step_candidates": [
        {"candidate_id": 1, "objective": "o2", "info_to_obtain": "i", "cmd": "echo d2c1bad"},
        {"candidate_id": 2, "objective": "o2b", "info_to_obtain": "i", "cmd": "echo d2sib"}]},
    {"depth": 3, "is_mission_complete": False, "next_step_candidates": [
        {"candidate_id": 1, "objective": "o3", "info_to_obtain": "i", "cmd": "echo NEEDS_PING"},
        {"candidate_id": 2, "objective": "o3b", "info_to_obtain": "i", "cmd": "echo d3sib"}]},
    {"depth": 4, "is_mission_complete": True, "next_step_candidates": []},
]
# one verdict per execution, in order (entry 6 is the ping step: _enforce_rc_floor forces BLOCKED, so its value is ignored)
DIGESTS = ["RAN_OK", "BAD_CMD", "BAD_CMD", "BAD_CMD", "RAN_OK", "RAN_OK", "RAN_OK"]
FIXES = ["echo fixed1", "echo fixed2"]
n = {"cand": 0, "digest": 0, "cmdfix": 0}


def fake_post_chat(model, messages, schema, name, **kw):
    if name == "cand":
        obj = CANDS[n["cand"]]; n["cand"] += 1
    elif name == "rank":
        obj = {"ranking": [{"candidate_id": 1}, {"candidate_id": 2}], "ranking_analysis": "t"}
    elif name == "digest":
        obj = {"verdict": DIGESTS[n["digest"]], "finding": "f"}
        n["digest"] += 1
    elif name == "cmdfix":
        obj = {"change": "c", "cmd": FIXES[n["cmdfix"]]}; n["cmdfix"] += 1
    else:
        raise AssertionError(f"unexpected post_chat name {name!r}")
    return obj, json.dumps(obj), "stop"


def fake_exec(cmd, timeout=30):
    if "NEEDS_PING" in cmd:        # pass the static filter (echo), but behave like a missing tool
        return 127, "", "bash: line 1: ping: command not found", 0.01
    return 0, "ok", "", 0.01


def main():
    exputil.post_chat = fake_post_chat
    status, depth = loop.run("fake-model", "test_run.json", max_steps=20, env_exec=fake_exec)
    run = json.loads((exputil.OUT / "test_run.json").read_text())

    fails = []
    def check(name, got, exp):
        ok = got == exp
        print(f"  {'ok ' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f" (expected {exp!r})"))
        if not ok:
            fails.append(name)

    check("final status", status, "complete_claimed")
    check("reached depth", depth, 4)
    check("fix_command calls (retry cap = 2)", n["cmdfix"], 2)
    # #1 fix: method_dead holds ONLY the genuinely-missing tool from the rc127 step,
    # NOT a working tool blamed by the BAD_CMD->BLOCKED escalation at d2.
    check("method_dead", run.get("method_dead"), ["ping"])
    # d2 chosen ended on the sibling (c2) after the escalation rolled back c1
    d2 = next(s for s in run["steps"] if s["depth"] == 2)
    check("d2 rolled back to sibling c2", d2["chosen_candidate_id"], 2)
    # d2 c1 kept its fix history (orig + 2 fixes = 3 attempts)
    check("d2 c1 fix_attempts length", len(d2.get("fix_attempts", [])), 3)

    print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
