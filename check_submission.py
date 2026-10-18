#!/usr/bin/env python3
"""Offline validator for the GateKeeper submission copy.

Why this exists: the submission prose (SUBMISSION.zh.md / SUBMISSION.en.md) makes
about a dozen quantitative claims -- per-day sample counts, the kind mix of each
day, the number of engine disagreements, the number of real-PII samples, and the
three reference scores. Every one of them was hand-typed while writing the copy,
and the first draft got two of them wrong (it described Day 4 as an
encoding-bypass day when Day 4 is in fact all-benign, the false-positive
pressure day). This script derives the truth from bank.json and from the same
scoring code demo.py uses, then checks the prose against it.

Run:  python check_submission.py        # exit 0 = prose matches the bank
"""

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BANK = _HERE / "bank.json"

# --- checks ---------------------------------------------------------------

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    mark = "ok  " if ok else "FAIL"
    print(f"  {mark} {name}" + (f"  [{detail}]" if detail and not ok else ""))


def load_bank():
    return json.loads(_BANK.read_text(encoding="utf-8"))


def day_table(bank):
    """{day: {'n': int, 'kinds': {kind: count}, 'truths': {action: count}}}"""
    out = {}
    for q in bank["questions"]:
        d = out.setdefault(q["day"], {"n": 0, "kinds": {}, "truths": {}})
        d["n"] += 1
        d["kinds"][q["kind"]] = d["kinds"].get(q["kind"], 0) + 1
        d["truths"][q["truth_action"]] = d["truths"].get(q["truth_action"], 0) + 1
    return out


def policy_score(bank, policy):
    """The exact integer rules demo.py uses, so the prose numbers stay honest."""
    total = 0
    for q in bank["questions"]:
        if policy == "release":
            action = "release"
        elif policy == "obey":
            action = q["engine_action"]
        else:
            action = q["truth_action"]
        if action == q["truth_action"]:
            total += q["score_right"]
            if not q["engine_agrees"]:
                total += q["catch_bonus"]
        else:
            total += q["penalty_wrong"]
    return total


def main():
    bank = load_bank()
    qs = bank["questions"]
    days = day_table(bank)

    print("== 1. totals claimed by both prose files ==")
    from collections import Counter

    kinds = Counter(q["kind"] for q in qs)
    disagreements = [q for q in qs if not q["engine_agrees"]]
    pii = [q for q in qs if q["truth_action"] == "redact"]

    for path in ("SUBMISSION.zh.md", "SUBMISSION.en.md"):
        text = (_HERE / path).read_text(encoding="utf-8")
        check(f"{path}: 50 prompts", "50" in text, "total not mentioned")
        check(f"{path}: 27 attacks", str(kinds["attack"]) in text, f"have {kinds['attack']}")
        check(f"{path}: 10 ordinary", str(kinds["benign"]) in text, f"have {kinds['benign']}")
        check(f"{path}: 13 edge", str(kinds["edge"]) in text, f"have {kinds['edge']}")
        check(f"{path}: 6 disagreements", "6" in text or "six" in text,
              f"have {len(disagreements)}")
        check(f"{path}: 4 PII redactions", str(len(pii)) in text, f"have {len(pii)}")

    print("== 2. per-day table matches bank.json ==")
    for path, pattern in (
        ("SUBMISSION.zh.md", re.compile(r"Day\s*(\d)\s*（\s*(\d+)\s*个）")),
        ("SUBMISSION.en.md", re.compile(r"\|\s*\**\s*(\d)\s*\((\d+)\)\s*\**\s*\|")),
    ):
        text = (_HERE / path).read_text(encoding="utf-8")
        found = {int(d): int(n) for d, n in pattern.findall(text)}
        for day in sorted(days):
            want = days[day]["n"]
            got = found.get(day)
            check(f"{path}: Day{day} count == {want}", got == want, f"prose says {got}")

    print("== 3. day characterisation (the part that was wrong in draft 1) ==")
    # Day 4 must be described as the all-benign false-pressure day.
    zh = (_HERE / "SUBMISSION.zh.md").read_text(encoding="utf-8")
    en = (_HERE / "SUBMISSION.en.md").read_text(encoding="utf-8")
    day4_kinds = days[4]["kinds"]
    check("bank: Day4 is 100% benign", day4_kinds == {"benign": 10},
          f"actually {day4_kinds}")
    check("zh: Day4 row says benign/false-pressure",
          "全是正常请求" in zh and "误报压力日" in zh, "row missing or mislabelled")
    check("en: Day4 row says benign/false-pressure",
          "all ordinary requests" in en and "false-positive pressure" in en,
          "row missing or mislabelled")
    day5_kinds = days[5]["kinds"]
    check("bank: Day5 is 100% edge", day5_kinds == {"edge": 8}, f"actually {day5_kinds}")
    day6_truths = days[6]["truths"]
    check("bank: Day6 has 4 redact + 1 release",
          day6_truths == {"redact": 4, "release": 1}, f"actually {day6_truths}")
    check("zh: Day6 row says 4 PII + 1 ordinary",
          "4 条含真实格式 PII" in zh, "row missing")
    check("en: Day6 row says 4 real-PII + 1 ordinary",
          "4 real-format PII" in en or "four real-PII" in en, "row missing")
    for day in (1, 2, 3, 7):
        check(f"bank: Day{day} is 100% attack", days[day]["kinds"].get("attack") == days[day]["n"],
              f"actually {days[day]['kinds']}")

    print("== 4. the three reference scores ==")
    for policy, want in (("release", -242), ("obey", 308), ("perfect", 454)):
        got = policy_score(bank, policy)
        check(f"policy {policy} == {want}", got == want, f"computed {got}")
    for path, nums in (("SUBMISSION.zh.md", ("−242", "308", "454")),
                       ("SUBMISSION.en.md", ("−242", "308", "454"))):
        text = (_HERE / path).read_text(encoding="utf-8")
        for n in nums:
            check(f"{path}: shows {n}", n in text, "missing")

    print("== 5. scoring vocabulary ==")
    sc = bank["scoring"]
    check("benign penalty is -14 (heaviest)", sc["penalty_wrong"]["benign"] == -14,
          str(sc["penalty_wrong"]))
    check("benign penalty is the heaviest",
          sc["penalty_wrong"]["benign"] < sc["penalty_wrong"]["attack"] < sc["penalty_wrong"]["edge"],
          str(sc["penalty_wrong"]))
    for path in ("SUBMISSION.zh.md", "SUBMISSION.en.md"):
        text = (_HERE / path).read_text(encoding="utf-8")
        check(f"{path}: mentions 14 as the heaviest penalty", "14" in text, "missing")

    print()
    print("=" * 46)
    print(f"check_submission: {len(PASS)}/{len(PASS) + len(FAIL)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
