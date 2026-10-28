The command did not run as the selected plan intended. Keep that intent and rewrite ONLY the command so it carries out the intent.

PLAN INTENT TO SATISFY:
  objective:       {{OBJECTIVE}}
  info_to_obtain:  {{INFO_TO_OBTAIN}}

Below are the commands you already tried for this intent, with the reason each one was wrong, ordered from oldest to newest:
{{HISTORY}}

Fix the CAUSE, not the surface: if a substituted value was the WRONG KIND (a fragment where the full value was needed, or the right content in the wrong form), put the value you actually observed — and if you have not observed it yet, make the new command OBSERVE it rather than guess another; if a range / variable did not expand, write it so it does; if it timed out, make it smaller / faster. Your new command MUST DIFFER from every one already tried above.

Output ONE JSON object, nothing else:
{
  "change": "<one line: what is different now and why it fixes the cause>",
  "cmd": "<the corrected shell command>"
}
