You just ran ONE step of your loop. Below is the step you planned and the RAW result of running its command. Distill what this step actually achieved into a compact record (a "digest"). Your future steps will read this digest instead of the full raw output, so it must be accurate and self-contained.

THE STEP JUST RUN:
{{STEP}}

Output ONE JSON object with these fields (the <...> says what each field holds; do not emit the <...> itself):

{
  "intended": "<what this step was trying to find out, in one phrase>",
  "observed": "<the FACTS of the result in one line: rc, elapsed, and the gist of the output — state it, do not interpret yet>",
  "verdict": "<EXACTLY ONE of: INFO_GAINED | RAN_BUT_EMPTY | BAD_CMD | BLOCKED>",
  "learned": "<if INFO_GAINED: the concrete fact or value obtained (e.g. a path, address, identity); else empty string>",
  "note": "<if NOT INFO_GAINED: what specifically went wrong, stated as a fact, in one line; else empty string>"
}

Pick the verdict by asking these FOUR questions IN ORDER. Use the FIRST one that matches — the
tests are a priority ladder, not a menu, so stop at the first YES.

1. BLOCKED — did the TOOL actually run? (NO -> BLOCKED)
   The program was missing or not executable (rc 127 / 126), or it was killed by a timeout before
   it could finish (rc 124). The command never produced a real result.
   BLOCKED is about the TOOL, NOT the network. An ssh / curl / nc that runs and then reports
   "No route to host", "could not resolve", "connection refused", or "network is unreachable"
   DID run — it is NOT BLOCKED. Fall through to the next questions (such a network result is
   usually RAN_BUT_EMPTY, or INFO_GAINED when the error itself is a fact you wanted, e.g.
   "connection refused" proves a host is alive at that address).

2. BAD_CMD — it ran, but did it do what you INTENDED? (NO -> BAD_CMD)
   The command executed but acted on something OTHER than what "intended" describes, so its
   result cannot answer your question. The fix is to REWRITE the command; the environment is fine.
   Tells (any one is enough):
   - a literal you wrote is still in the output verbatim (a `{...}` range, a `$var`) -> the shell
     never expanded it;
   - a substituted value is the WRONG KIND for the goal — e.g. you meant to reach a network
     address but the output shows it contacting a bare number like `10` instead of a full dotted
     address `10.x.x.x`, or a path fragment instead of a full path;
   - a network / scan / ssh command returned in under ~0.1s (it never really tried);
   - the number of output lines is far from what the command should have produced.

3. INFO_GAINED — did you obtain a concrete NEW fact? (YES -> INFO_GAINED)
   The output contains a fact that advances the search: a path, an address, an identity, or the
   confirmed existence of a file / directory / host — even if it is not yet the final answer
   (a directory that might hold the key still counts). Record that fact in "learned".

4. RAN_BUT_EMPTY — none of the above.
   The command was sound and its result is TRUSTWORTHY, but it yielded NO new fact: an empty
   listing, no match, a host that is simply absent. A reliable "nothing is here".

Always read the OUTPUT TEXT, never rc alone: `cmd || echo ...` and `2>/dev/null` can make a real
failure show rc=0. If the text says "No response" / "failed" though rc=0, it is NOT INFO_GAINED.

Keep EVERY field to one line. State only the facts the output actually shows; do NOT recommend a
next action — only record what happened. Never invent a result that is not there.
