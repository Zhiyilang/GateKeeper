#!/usr/bin/env python3
"""GATEKEEPER offline evaluation suite (stdlib only, no network).

Two layers:

1. Always: validate the shipped bank.json (check_bank.py). This needs nothing
   but the JSON file, so it runs identically on CI and on a laptop.

2. If the sibling AuditPilot checkout is present: rebuild the bank from the
   live engine and assert the result is byte-identical to the shipped one.
   That is the assertion which keeps the answer key honest - if someone edits
   bank.json by hand, or the engine drifts, this fails. When AuditPilot is
   absent (CI, where this repo has no sibling) the layer is skipped loudly,
   never silently.

A hostile-locale subprocess (LC_ALL=C without PYTHONUTF8) is run for real;
set GATEKEEPER_SKIP_LOCALE=1 when invoking from inside that subprocess to
avoid recursion.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VENDOR = _HERE.parent / "auditpilot"
PY = sys.executable

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL {name} -- {detail}")
    return bool(cond)


def _run(args: list[str], env_extra: dict | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    p = subprocess.run([PY] + args, cwd=str(_HERE), env=env,
                       capture_output=True, text=True, errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    print("== A. bank validation (always) ==", flush=True)
    rc, out = _run(["check_bank.py"])
    check("check_bank.exit0", rc == 0, f"rc={rc}\n{out[-800:]}")
    check("check_bank.all_pass", "0 failed" in out, "validator reported failures")

    print("\n== B. rebuild from the live engine (needs ../auditpilot) ==", flush=True)
    if (_VENDOR / "auditpilot" / "agentguard.py").exists():
        shipped = (_HERE / "bank.json").read_bytes()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "bank.json"
            # Runs in place (never copied): build_bank.py resolves AuditPilot
            # relative to its own location, so moving it would break the
            # vendor lookup. --out redirects the artefact instead.
            rc, out = _run(["build_bank.py", "--out", str(out_path)])
            check("build.exit0", rc == 0, f"rc={rc}\n{out[-800:]}")
            fresh = out_path.read_bytes() if out_path.exists() else b""
        check("build.deterministic", fresh == shipped,
              "rebuilt bank differs from the shipped one - the answer key is stale")
    else:
        print("  skip  ../auditpilot not present; rebuild parity not checked here")
        check("rebuild.skipped_explicitly", True, "")

    print("\n== C. hostile locale (LC_ALL=C, no PYTHONUTF8) ==", flush=True)
    if os.environ.get("GATEKEEPER_SKIP_LOCALE") == "1":
        print("  skip  running inside the hostile-locale subprocess")
        check("locale.self_skip", True, "")
    else:
        env = {"LC_ALL": "C", "LANG": "C", "GATEKEEPER_SKIP_LOCALE": "1"}
        for k in ("PYTHONUTF8", "PYTHONIOENCODING"):
            os.environ.pop(k, None)
        rc, out = _run(["eval.py"], env)
        check("locale.exit0", rc == 0, f"rc={rc}\n{out[-800:]}")
        check("locale.no_traceback", "Traceback" not in out, out[-500:])

    total = PASS + FAIL
    print(f"\n{'=' * 46}")
    print(f"GATEKEEPER eval: {PASS}/{total} passed, {FAIL} failed")
    if FAILURES:
        print("failures:")
        for f in FAILURES:
            print("  - " + f)
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
