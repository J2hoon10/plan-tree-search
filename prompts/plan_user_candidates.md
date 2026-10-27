This is one step of your loop. Look at the current state and propose the candidate next steps — the branches of a search tree over the mission. Exactly one candidate will be chosen and executed; its result comes back, and only then do you decide the following step.

CURRENT STATE:
{{STATE}}

Output ONE JSON object with these fields (the <...> text says what each field holds; do not emit the <...> itself):

{
  "depth": <tree level of this step: mission start = root = depth 0, first step = depth 1, +1 for each chosen step>,
  "is_mission_complete": <DECIDE THIS FIRST, before writing candidates: true if an observed result already shows the mission is done, else false>,
  "next_step_candidates": [
    {
      "candidate_id": <1-based integer, unique within this step>,
      "precondition": "<the state this candidate assumes before it runs>",
      "objective": "<the goal of this step>",
      "info_to_obtain": "<the one piece of information this step yields>",
      "cmd": "<the single shell command that yields it>"
    }
  ]
}

Rules:
- next_step_candidates: EXACTLY 3 candidates when is_mission_complete is false; an empty list [] when it is true.
- The 3 candidates must be DIFFERENT kinds of action / method. Two that differ only in a literal (another path, address, or filename) count as the same kind — not allowed.
- Pair each info_to_obtain with exactly one cmd that yields it (1:1). The cmd goes in the cmd field as a shell command: no prose, no comments, no numbering.
- Early on, prefer candidates that OBSERVE the situation over ones that SEARCH BY A GUESS. To OBSERVE is to establish what is actually there before targeting anything: confirm the real directory structure and the files that exist, and read your own identity, privileges, address, and subnet. Do not search for — or put in a cmd — a filename, path, or address you have only guessed; when you don't yet know where something is, first enumerate what exists, then target what you actually saw.
- Judge is_mission_complete only from observed results; never guess completion.
