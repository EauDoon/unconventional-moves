#!/usr/bin/env python3
"""Local authoring and review utilities. Never execute the proposed moves."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .validate_plan import read_json_file, validate_plan_data
except ImportError:
    from validate_plan import read_json_file, validate_plan_data

ROOT = Path(__file__).resolve().parents[1]


def read_plan(path: Path) -> dict:
    plan = read_json_file(path)
    failures = validate_plan_data(plan)
    if failures:
        raise ValueError("Invalid plan: " + "; ".join(failures))
    return plan


def emit(content: str, output: Path | None) -> None:
    if output is None:
        print(content, end="" if content.endswith("\n") else "\n")
    else:
        # Exclusive creation protects existing drafts, symlinks, and input files.
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Copy a complete synthetic language-practice plan for editing")
    init.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            plan = read_plan(ROOT / "examples/bounded-plan.json")
            emit(json.dumps(plan, indent=2) + "\n", args.output)
    except FileExistsError:
        print("FAIL output already exists; choose a new path", file=sys.stderr)
        return 1
    except (OSError, UnicodeError):
        print("FAIL input or output file is unavailable or not UTF-8", file=sys.stderr)
        return 1
    except ValueError as exc:
        print("FAIL " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
