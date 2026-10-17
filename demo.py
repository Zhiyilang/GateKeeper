#!/usr/bin/env python3
"""GATEKEEPER demo: three operators play the same shift, nobody types.

Non-interactive on purpose - it has to run on CI. Instead of asking a human,
it simulates three policies over the same question bank:

  release-everything  waves every request through
  obey-the-engine     copies whatever the gateway suggested
  perfect-operator    answers with the authored ground truth

The gap between "obey-the-engine" and "perfect-operator" is the entire
argument for the game: a human who defers to the machine inherits every one
of the machine's blind spots, and the bank records exactly six places where
the machine is wrong.

stdlib only. Deterministic: no RNG, no clock, no network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def load_bank() -> dict:
    return json.loads((_HERE / "bank.json").read_text(encoding="utf-8"))


def play(questions: list[dict], policy: str) -> dict:
    score = 0
    caught = 0
    missed_attacks = 0
    false_blocks = 0
    for q in questions:
        if policy == "release-everything":
            answer = "release"
        elif policy == "obey-the-engine":
            answer = q["engine_action"]
        elif policy == "perfect-operator":
            answer = q["truth_action"]
        else:
            raise ValueError(policy)

        if answer == q["truth_action"]:
            score += q["score_right"]
            if not q["engine_agrees"]:
                score += q["catch_bonus"]
                caught += 1
        else:
            score += q["penalty_wrong"]
            if q["kind"] == "attack":
                missed_attacks += 1
            if q["kind"] == "benign":
                false_blocks += 1
    return {"score": score, "caught": caught,
            "missed_attacks": missed_attacks, "false_blocks": false_blocks}


def main() -> int:
    bank = load_bank()
    questions = bank["questions"]

    print("GATEKEEPER - one shift, three operators")
    print("prompts: %d   engine wrong on: %d"
          % (len(questions), sum(1 for q in questions if not q["engine_agrees"])))
    print()

    results = {}
    for policy in ("release-everything", "obey-the-engine", "perfect-operator"):
        results[policy] = play(questions, policy)

    width = max(len(p) for p in results)
    print(f"{'policy'.ljust(width)}  {'score'.rjust(6)}  "
          f"{'caught'.rjust(6)}  {'missed attacks'.rjust(14)}  {'false blocks'.rjust(12)}")
    print("-" * (width + 46))
    for policy, r in results.items():
        print(f"{policy.ljust(width)}  {r['score']:6d}  {r['caught']:6d}  "
              f"{r['missed_attacks']:14d}  {r['false_blocks']:12d}")

    print()
    gap = results["perfect-operator"]["score"] - results["obey-the-engine"]["score"]
    print("obeying the engine costs %d points versus playing it yourself." % gap)
    print("that gap is the game: you are supervising the gateway, not obeying it.")

    obey = results["obey-the-engine"]
    perfect = results["perfect-operator"]
    if obey["score"] >= perfect["score"]:
        print("DEMO_FAIL: deferring to the engine should never beat the operator")
        return 1
    if results["release-everything"]["missed_attacks"] == 0:
        print("DEMO_FAIL: waving everything through must let attacks pass")
        return 1
    print("DEMO_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
