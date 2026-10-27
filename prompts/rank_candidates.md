You are choosing the NEXT step of your loop. Below are the candidate next steps you just proposed — they have NOT been run yet. Using only the CURRENT STATE (the prior steps already taken and their results) and each candidate's own objective / info_to_obtain / command, decide which one to run next. Write the reasoning BEFORE the decision.

CURRENT STATE (steps already taken on the chosen path, with their results):
{{STATE}}

CANDIDATES (proposed at this depth, not yet run):
{{CANDIDATES}}

Rank the candidates. First write `ranking_analysis`: compare the candidates against the mission and against each other, referring to candidate_ids. Then in `ranking`, order ALL the candidates above from the BEST next step FIRST to the worst LAST, by your own judgment of which most advances the mission from the current state. There is no fixed rubric or score.

Output ONE JSON object, with the fields in THIS order:
{
  "ranking_analysis": "<compare the candidates against the mission and against each other; refer to candidate_ids>",
  "ranking": [ {"candidate_id": <int>} ]
}
