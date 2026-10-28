You just ran ONE step of your loop. Below is the step you planned and the RAW result of running its command. Distill what this step actually achieved into a compact record (a "digest"). Your future steps will read this digest instead of the full raw output, so its content must be correct, and it must make sense on its own — readable without going back to the raw output.

THE STEP JUST RUN:
{{STEP}}

Decide the verdict with this decision tree: test 1, then 2, then 3, and STOP at the FIRST branch whose condition is TRUE — that branch is your verdict.

1. BLOCKED — the program itself never started.  [YES -> BLOCKED | NO -> go to 2]
   The shell could not launch the command, so there is NO result about your task. Either of these two cases means BLOCKED:
   - The program is not installed here: the output says "command not found", or rc is 127.
   - The program exists but cannot run: the output says "not executable" or "permission denied" ON THE PROGRAM, or rc is 126.

2. BAD_CMD — the command ran, but acted on something OTHER than your intent.  [YES -> BAD_CMD | NO -> go to 3]
   Its result answers a different question than the one "intended" asked, so REWRITE the command; the environment is fine. Any of these signs means BAD_CMD:
   - A literal you wrote is still sitting in the output (a `{...}` range, a `$var`). The shell passed it through as text instead of expanding it.
   - A substituted value is the WRONG KIND for the goal. The command acted on a partial or mis-typed value — a fragment where the full value was needed, or the right content in the wrong form — instead of the complete value the step aimed at.
   - The command returned in under ~0.1s, too fast to have done the work, or it timed out with rc 124, too slow.
   - The output has far more or far fewer lines than this command should produce.

3. RAN_OK — the command ran and its result is TRUSTWORTHY.  [YES -> RAN_OK]
   You got a real, trustworthy answer about your task. Either of these two kinds means RAN_OK:
   - A FACT you found: a path, an address, an identity, or a file/directory/host that exists.
   - A trustworthy ABSENCE: an empty listing, a "no match", or a lookup that returns nothing where you searched. An absence is also a fact; it rules a place out and tells you where to go next.

Always read the OUTPUT TEXT, never rc alone: `cmd || echo ...` and `2>/dev/null` can make a real failure show rc=0. If the text says "No response" / "failed" though rc=0, record that absence in finding.

Keep EVERY field to one line. State only the facts the output actually shows; do NOT recommend a next action — only record what happened.

Output ONE JSON object with these fields (the <...> says what each field holds; do not emit the <...> itself):

{
  "verdict": "<EXACTLY ONE of: RAN_OK | BAD_CMD | BLOCKED>",
  "finding": "<one line: the durable fact this step established, written so a later step can act on it. Fill it by verdict:
     - RAN_OK: what the result CONFIRMED about the environment — a thing that EXISTS (its value plus the attributes a next step needs: a path with its owner and mode; an address tagged with WHOSE it is) OR an ABSENCE (the place you checked and found nothing, named so it is ruled out).
     - BLOCKED: which tool or program is unusable here and why it could not launch. State it as a general fact, not tied to this one command, so a later step does not try the same tool again.
     - BAD_CMD: empty string — the command will be rewritten, so nothing is recorded.
     State only what the output directly shows; do not interpret.>"
}
