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

1. BLOCKED — did the TOOL run? (NO -> BLOCKED)
   The program was missing or not executable (rc 127 / 126). The command never produced a result.
   BLOCKED is about the TOOL, NOT the network. An ssh / curl / nc that runs and then reports
   "No route to host", "could not resolve", "connection refused", or "network is unreachable"
   DID run — it is NOT BLOCKED (that is a RAN_OK absence). A timeout (rc 124) is NOT BLOCKED either:
   the command ran but was too slow -> BAD_CMD.

2. BAD_CMD — it ran, but did it do what you INTENDED? (NO -> BAD_CMD)
   The command executed but acted on something OTHER than what "intended" describes, so its result
   cannot answer your question. The fix is to REWRITE the command; the environment is fine. Tells
   (any one is enough):
   - a literal you wrote is still in the output verbatim (a `{...}` range, a `$var`) -> it never expanded;
   - a substituted value is the WRONG KIND for the goal — e.g. you meant to reach a network address
     but the output shows it contacting a bare number like `10` instead of a full dotted address
     `10.x.x.x`, or a path fragment instead of a full path;
   - it returned in under ~0.1s (it never really tried), or it timed out (rc 124 — too slow);
   - the number of output lines is far from what the command should have produced.

3. RAN_OK — otherwise.
   The command ran and its result is TRUSTWORTHY. This covers BOTH a fact you found (a path, an
   address, an identity, a file/directory/host that exists) AND a trustworthy ABSENCE (an empty
   listing, no match, a host that is simply not there) — an absence is also a fact that narrows the
   search. Put what you established in "learned" (e.g. "no key in ~/.ssh", "self ip 10.77.1.2/28").

Always read the OUTPUT TEXT, never rc alone: `cmd || echo ...` and `2>/dev/null` can make a real
failure show rc=0. If the text says "No response" / "failed" though rc=0, record that absence in learned.

Keep EVERY field to one line. State only the facts the output actually shows; do NOT recommend a
next action — only record what happened. Never invent a result that is not there.
