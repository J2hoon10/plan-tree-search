You ran a command for a goal, but it did NOT do what you intended — the goal is still unmet. Keep the SAME goal; rewrite ONLY the command so it actually does it.

GOAL (do not change):
  objective:    {{OBJECTIVE}}
  info sought:  {{INFO}}
  precondition: {{PRECONDITION}}

Commands you already tried for this goal, and why each was wrong (oldest -> newest):
{{HISTORY}}

Fix the CAUSE, not the surface: if a substituted value was the WRONG KIND (an address shown as a
bare number like `10` instead of a full dotted address `10.x.x.x`, a path fragment instead of a
full path, ...), put the real value; if a range / variable did not expand, write it so it does; if
it timed out, make it smaller / faster. Your new command MUST DIFFER from every one already tried
above. Do NOT change the goal.

Output ONE JSON object, nothing else:
{
  "change": "<one line: what is different now and why it fixes the cause>",
  "cmd": "<the corrected shell command>"
}
