This is one step of your loop. Look at STEP_HISTORY and propose the candidate next steps — the branches of a search tree over the mission.

STEP_HISTORY:
{{STEP_HISTORY}}

Output ONE JSON object with these fields (the <...> text says what each field holds; do not emit the <...> itself):

{
  "depth": <tree level of this step: mission start = root = depth 0, first step = depth 1, +1 for each chosen step>,
  "findings": "<read STEP_HISTORY and state in one line what has ALREADY been established — the facts confirmed and the places or tools ruled out. Describe only; do NOT prescribe a next action.>",
  "is_mission_complete": <DECIDE THIS before writing candidates: true if findings already show the mission is done, else false>,
  "next_step_candidates": [
    {
      "candidate_id": <1-based integer, unique within this step>,
      "objective": "<the information or work still needed to accomplish the mission (not already in findings); the 3 candidates must each pursue a DIFFERENT one>",
      "info_to_obtain": "<the information you expect this step to yield>",
      "cmd": "<the single shell command that yields this candidate's info_to_obtain>"
    }
  ]
}

Rules:
- next_step_candidates: EXACTLY 3 candidates when is_mission_complete is false; an empty list [] when it is true.
- The 3 candidates must be DIFFERENT kinds of action / method. Two that differ only in a literal (another path, address, or filename) count as the same kind — not allowed.
- Pair each info_to_obtain with exactly one cmd that yields it (1:1). The cmd goes in the cmd field as a shell command: no prose, no comments, no numbering.
- Early on, prefer candidates that OBSERVE the situation over ones that SEARCH BY A GUESS. To OBSERVE is to establish what is actually there before targeting anything: confirm the real directory structure and the files that exist, and read your own identity, privileges, address, and subnet. Do not search for — or put in a cmd — a filename, path, or address you have only guessed; when you don't yet know where something is, first enumerate what exists, then target what you actually saw.
- Judge is_mission_complete only from observed results; never guess completion.
