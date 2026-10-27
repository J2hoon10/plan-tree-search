Look at the CURRENT STATE and choose, from the plan candidates you just proposed, which one is the most appropriate next step to advance the mission. Exactly one candidate will be chosen and run. Using only the CURRENT STATE (the prior steps already taken and their results) and each candidate's own objective / info_to_obtain / command, decide which one to run next. Write the reasoning BEFORE the decision.

CURRENT STATE (steps already taken on the chosen path, with their results):
{{STATE}}

CANDIDATES (proposed at this depth, pending your choice):
{{CANDIDATES}}

Do these two steps IN ORDER:
1. Write `ranking_analysis`: compare the candidates against the mission and against each other, referring to candidate_ids.
2. Write `ranking`: based only on the analysis from step 1, order ALL the candidates above from the BEST next step FIRST to the worst LAST, judged by which most advances the mission from the current state.

Output ONE JSON object, with the fields in THIS order:
{
  "ranking_analysis": "<compare the candidates against the mission and against each other; refer to candidate_ids>",
  "ranking": [ {"candidate_id": <int>} ]
}
