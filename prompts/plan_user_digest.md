You just ran ONE step of your loop. Below is the step you planned and the RAW result of running its command. Distill what this step actually achieved into a compact record (a "digest"). Your future steps will read this digest instead of the full raw output, so it must be accurate and self-contained.

THE STEP JUST RUN:
{{STEP}}

Output ONE JSON object with these fields (the <...> says what each field holds; do not emit the <...> itself):

{
  "intended": "<what this step was trying to find out, in one phrase>",
  "observed": "<the FACTS of the result in one line: rc, elapsed, and the gist of the output — state it, do not interpret yet>",
  "verdict": "<EXACTLY ONE of: RAN_OK | BAD_CMD | BLOCKED>",
  "learned": "<if RAN_OK: the fact established — presence OR absence (e.g. a path, an address, 'no key in ~/.ssh'); else empty string>",
  "note": "<if BAD_CMD or BLOCKED: what specifically went wrong, stated as a fact, in one line; else empty string>"
}

Pick the verdict by asking these THREE questions IN ORDER. Use the FIRST one that matches.

1. BLOCKED — the program itself never started. (YES -> BLOCKED)
   The shell could not launch the command, so there is NO result about your task. Exactly two cases:
   - "command not found" / rc 127  — the program is not installed here, or
   - "not executable" / "permission denied" ON THE PROGRAM / rc 126.
   That is the whole list for BLOCKED.

2. BAD_CMD — the command ran, but acted on something OTHER than your intent. (YES -> BAD_CMD)
   Its result answers a different question than the one "intended" asked, so REWRITE the command
   (the environment is fine). Any one of these signs means BAD_CMD:
   - a literal you wrote is still sitting in the output (a `{...}` range, a `$var`) — the shell
     passed it through as text instead of expanding it;
   - a substituted value is the WRONG KIND for the goal — you aimed at a network address but it
     contacted a bare number like `10` instead of a full dotted address `10.x.x.x`, or a path
     fragment instead of a full path;
   - it returned in under ~0.1s (too fast to have done the work), or it timed out (rc 124, too slow);
   - the output has far more or far fewer lines than this command should produce.

3. RAN_OK — the command ran and its result is TRUSTWORTHY. (YES -> RAN_OK)
   You got a real answer about your task, and it is one of two kinds:
   - a FACT you found: a path, an address, an identity, a file/directory/host that exists; or
   - a trustworthy ABSENCE: an empty listing, "no match", a host that is not there, a name that
     does not resolve. An absence is also a fact — it rules a place out and tells you where to go next.
   Put what you established in "learned" (e.g. "no key in ~/.ssh", "self ip 10.77.1.2/28",
   "target-node has no DNS name, must find its IP").

Always read the OUTPUT TEXT, never rc alone: `cmd || echo ...` and `2>/dev/null` can make a real
failure show rc=0. If the text says "No response" / "failed" though rc=0, record that absence in learned.

Keep EVERY field to one line. State only the facts the output actually shows; do NOT recommend a
next action — only record what happened. Never invent a result that is not there.
