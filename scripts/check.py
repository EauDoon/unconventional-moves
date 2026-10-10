#!/usr/bin/env python3
"""Run the repository check set that CI runs, in order, with one command.

Each check runs under the current interpreter from the repository root. The
script stops at the first failing check and exits with its code. The package
is built into a fresh temporary directory, so nothing is left in the checkout.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from .versioning import VersionAction
except ImportError:
    from versioning import VersionAction

ROOT = Path(__file__).resolve().parents[1]
DIST = "<temporary directory>/dist"

# .github/workflows/ci.yml runs this script, so this list is the CI check set.
CHECKS: tuple[tuple[str, ...], ...] = (
    ("scripts/validate.py",),
    ("scripts/validate_plan.py", "examples/example-plan.json"),
    ("scripts/validate_plan.py", "examples/bounded-plan.json", "--json"),
    ("scripts/moves.py", "outcome", "examples/bounded-plan.json", "examples/bounded-outcome.json"),
    ("-m", "unittest", "discover", "-s", "tests", "-v"),
    ("evals/runner.py",),
    ("scripts/package.py", "--output", DIST),
)


def describe(check: tuple[str, ...]) -> str:
    return " ".join(("python", *check))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action=VersionAction)
    parser.add_argument("--list", action="store_true", help="print the commands without running them")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    if args.list:
        for check in CHECKS:
            print(describe(check))
        return 0
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    # Pass -B through so `python -B scripts/check.py` writes no bytecode caches.
    interpreter = [sys.executable, *(["-B"] if sys.flags.dont_write_bytecode else [])]
    with TemporaryDirectory(prefix="unconventional-moves-check-") as temporary:
        dist = str(Path(temporary) / "dist")
        for check in CHECKS:
            heading = "== " + describe(check)
            print(("::group::" + heading) if in_actions else heading, flush=True)
            result = subprocess.run([*interpreter, *(dist if part == DIST else part for part in check)], cwd=ROOT)
            if in_actions:
                print("::endgroup::", flush=True)
            if result.returncode != 0:
                print(f"FAIL {describe(check)} exited with code {result.returncode}", flush=True)
                return result.returncode
    print(f"PASS all {len(CHECKS)} checks", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
