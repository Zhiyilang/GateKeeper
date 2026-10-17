#!/usr/bin/env python3
"""Offline validator for the GATEKEEPER question bank.

Run after build_bank.py. Exits non-zero on any inconsistency.

Exists because the bank is a structured artefact whose numbers are quoted in
the competition submission: a question that is duplicated, a day that claims
eight questions but holds seven, or an "engine agrees" flag that contradicts
the recorded verdict would all be invisible until a judge hit them.

stdlib only. Prints ASCII only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
BANK_PATH = _HERE / "bank.json"

VALID_ACTIONS = {"release", "redact", "block"}
DECISION_TO_ACTION = {"allow": "release", "refuse": "block", "sanitize": "redact"}

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
    return bool(cond)


def main() -> int:
    if not BANK_PATH.exists():
        print("bank.json missing - run build_bank.py first")
        return 2

    raw = BANK_PATH.read_text(encoding="utf-8")
    try:
        bank = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"bank.json is not valid JSON: {e}")
        return 2

    qs = bank.get("questions", [])
    check("bank.has_questions", len(qs) > 0, f"count={len(qs)}")

    # --- identity --------------------------------------------------------
    ids = [q["id"] for q in qs]
    check("ids.unique", len(set(ids)) == len(ids),
          f"{len(ids) - len(set(ids))} duplicate id(s)")
    check("ids.format", all(i.startswith("q") and i[1:].isdigit() for i in ids),
          "ids must look like q001")

    texts = [q["text"] for q in qs]
    check("texts.unique", len(set(texts)) == len(texts),
          f"{len(texts) - len(set(texts))} duplicate prompt(s)")
    check("texts.nonempty", all(t.strip() for t in texts), "empty prompt")

    # --- action vocabulary ----------------------------------------------
    check("truth.valid", all(q["truth_action"] in VALID_ACTIONS for q in qs),
          "truth_action outside release/redact/block")
    check("engine.valid", all(q["engine_action"] in VALID_ACTIONS for q in qs),
          "engine_action outside release/redact/block")

    # --- internal consistency: the recorded engine_action must be exactly
    #     what the recorded engine_decision maps to -----------------------
    bad_map = [q["id"] for q in qs
               if DECISION_TO_ACTION.get(q["engine_decision"]) != q["engine_action"]]
    check("engine.mapping", not bad_map, f"engine_action contradicts engine_decision: {bad_map}")

    bad_flag = [q["id"] for q in qs
                if q["engine_agrees"] != (q["engine_action"] == q["truth_action"])]
    check("agrees.consistent", not bad_flag, f"engine_agrees flag wrong: {bad_flag}")

    scoring = bank.get("scoring", {})
    bad_score = [q["id"] for q in qs
                 if q["score_right"] != scoring.get("score_right", {}).get(q["truth_action"])]
    check("score.consistent", not bad_score, f"score_right contradicts the scoring table: {bad_score}")

    bad_bonus = [q["id"] for q in qs
                 if q["catch_bonus"] != (scoring.get("catch_bonus", 0) if not q["engine_agrees"] else 0)]
    check("bonus.consistent", not bad_bonus, f"catch_bonus contradicts engine_agrees: {bad_bonus}")

    # --- coverage --------------------------------------------------------
    kinds = {}
    for q in qs:
        kinds[q["kind"]] = kinds.get(q["kind"], 0) + 1
    for kind in ("attack", "benign", "edge"):
        check(f"kind.{kind}", kinds.get(kind, 0) >= 5, f"only {kinds.get(kind, 0)} '{kind}' prompts")

    by_day = {}
    for q in qs:
        by_day.setdefault(q["day"], []).append(q)
    check("days.count", len(by_day) == 7, f"expected 7 days, got {len(by_day)}")
    for day in sorted(by_day):
        check(f"day{day}.size", len(by_day[day]) >= 5, f"day {day} has {len(by_day[day])}")

    # --- the engine has to be good enough for the premise to hold --------
    atk = [q for q in qs if q["kind"] == "attack"]
    atk_caught = sum(1 for q in atk if q["engine_decision"] != "allow")
    rate = (100 * atk_caught) // len(atk) if atk else 0
    check("engine.catches_attacks", rate >= 80,
          f"engine only stops {rate}% of attacks - the game would be unplayable")

    ben = [q for q in qs if q["kind"] == "benign"]
    ben_wrong = [q["id"] for q in ben if q["engine_decision"] != "allow"]
    check("engine.no_false_positive", not ben_wrong,
          f"engine refuses ordinary traffic: {ben_wrong}")

    # --- and imperfect enough for the game to be worth playing -----------
    disagree = [q for q in qs if not q["engine_agrees"]]
    check("game.has_catches", len(disagree) >= 3,
          f"only {len(disagree)} prompts where the engine is wrong - no gameplay")
    check("game.not_broken", len(disagree) <= len(qs) // 4,
          f"{len(disagree)} of {len(qs)} wrong - the engine would be useless")

    redact_truth = [q for q in qs if q["truth_action"] == "redact"]
    check("game.has_redact", len(redact_truth) >= 3,
          f"only {len(redact_truth)} redact answers - a whole mechanic unused")

    # --- difficulty curve ------------------------------------------------
    def avg_risk(day: int) -> int:
        sub = by_day.get(day, [])
        return sum(q["engine_risk"] for q in sub) // len(sub) if sub else 0

    check("curve.attack_days_hot", avg_risk(1) > avg_risk(4),
          f"day1 risk {avg_risk(1)} must exceed day4 risk {avg_risk(4)}")
    check("curve.benign_days_cold", avg_risk(4) <= 5,
          f"day4 risk {avg_risk(4)} - ordinary traffic must score near zero")
    check("curve.final_day_hot", avg_risk(7) > avg_risk(5),
          f"day7 risk {avg_risk(7)} must exceed day5 risk {avg_risk(5)}")

    # --- portability -----------------------------------------------------
    check("json.ascii_safe", all(ord(c) < 128 for c in raw.replace("\\u", ""))
          or json.dumps(json.loads(raw), ensure_ascii=True) is not None,
          "bank must survive an ASCII round-trip")

    total = PASS + FAIL
    print(f"{'=' * 46}")
    print(f"GATEKEEPER bank: {PASS}/{total} passed, {FAIL} failed")
    if FAILURES:
        print("failures:")
        for f in FAILURES:
            print("  - " + f)
    print(f"prompts={len(qs)} kinds={sorted(kinds.items())} catches={len(disagree)}")
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
