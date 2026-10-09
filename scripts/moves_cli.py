#!/usr/bin/env python3
"""Version-aware CLI shim for scripts/moves.py.

Thin wrapper that reads a plan's contract_version and forwards every
argument to moves.main() unchanged. The shim exists so a v0.2-only
command (card, debrief, handoff, limits, observation-draft, outcome,
record, screen, select, table, timeline) refuses a v0.1 input with a
clear message at the CLI boundary, instead of letting moves.py raise a
less specific ValueError after parsing the plan.

The underlying moves.py stays untouched and remains the single source of
truth for behavior. This shim only inspects the input file and applies a
gate. Top-level options such as --version pass through to moves.py.

Rules:
- plan-required commands, using the first positional plan path:
  v0.2-only commands on a v0.1 plan are refused with exit 1.
  shared commands pass through to moves.main() unchanged.
  Optional flags may precede the plan; every moves.py option takes a value.
- plan-less commands (init, verify-handoff, unpack-handoff): pass through directly.
- unknown contract_version: refused with exit 1.
- no argv: delegated so argparse prints its usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from . import moves
    from .validate_plan import read_json_file
except ImportError:
    import moves
    from validate_plan import read_json_file


SUPPORTED_VERSIONS = {"unconventional-moves/v0.1", "unconventional-moves/v0.2"}

# Commands that require a v0.2 plan (selected_move_id and experiment cards).
# Every command below reaches moves.selected_move(), so a v0.1 plan cannot be
# served by them. Keep this list aligned with the commands that read the
# selected move; a command missing here fails later with the generic
# "experiment workflow requires a version 0.2 plan" message.
V02_REQUIRED_COMMANDS = frozenset({
    "card", "debrief", "handoff", "limits", "observation-draft", "outcome",
    "record", "screen", "select", "table", "timeline",
})

# Commands that accept either v0.1 or v0.2 plans at argv[1].
SHARED_COMMANDS = frozenset({
    "render", "review", "sources",
})

# compare reads two plans, so argv[1] is only one of them; it is gated by plan
# validation in moves.py rather than here and works on either version.

# Commands that take no plan argument and skip version detection.
NO_PLAN_COMMANDS = frozenset({"init", "verify-handoff", "unpack-handoff"})


def detect_version(plan_path: Path) -> str | None:
    """Return the contract_version from a plan file, or None on parse error.

    Use the same bounded reader as moves.py. A separate json.loads call
    accepts non-finite numbers, duplicate keys, and nesting deep enough
    to raise RecursionError before the command's own parser can refuse it.
    """
    try:
        data = read_json_file(plan_path)
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("contract_version")
    return value if isinstance(value, str) else None


def plan_argument(argv: list[str]) -> str | None:
    """Return the first positional argument.

    argparse accepts options before the plan path. Every option in moves.py
    takes one value, including the ``--name=value`` form. Treating argv[1]
    as the plan skips the version gate whenever a flag comes first.
    """
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            return argv[index + 1] if index + 1 < len(argv) else None
        if arg.startswith("-"):
            index += 1 if "=" in arg else 2
            continue
        return arg
    return None


def gate_version(command: str, argv: list[str]) -> int | None:
    """Return a non-zero exit code to refuse, or None to pass through."""
    if not argv:
        return None
    if command in NO_PLAN_COMMANDS:
        return None
    if command not in V02_REQUIRED_COMMANDS and command not in SHARED_COMMANDS:
        return None
    plan = plan_argument(argv)
    if plan is None:
        return None
    plan_path = Path(plan)
    if not plan_path.exists():
        return None
    version = detect_version(plan_path)
    if version is None:
        return None
    if version not in SUPPORTED_VERSIONS:
        print("FAIL unsupported contract_version: " + json.dumps(version, ensure_ascii=True)[1:-1], file=sys.stderr)
        return 1
    if command in V02_REQUIRED_COMMANDS and version == "unconventional-moves/v0.1":
        print(
            "FAIL " + command + " requires a v0.2 plan; input declares " + version,
            file=sys.stderr,
        )
        return 1
    return None


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        refusal = gate_version(argv[0], argv)
        if refusal is not None:
            return refusal
    return moves.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
