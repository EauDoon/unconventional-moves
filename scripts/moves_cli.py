#!/usr/bin/env python3
"""Version-aware CLI shim for scripts/moves.py.

Thin wrapper that reads a plan's contract_version and forwards every
argument to moves.main() unchanged. The shim exists so a v0.2-only
command (card, outcome, select, observation-draft, handoff) refuses a
v0.1 input with a clear message at the CLI boundary, instead of letting
moves.py raise a less specific ValueError after parsing the plan.

The underlying moves.py stays untouched and remains the single source of
for behavior. This shim only inspects the input file and applies a gate.

Rules:
- plan-required commands at argv[1]:
  v0.2-only commands on a v0.1 plan are refused with exit 1.
  shared commands pass through to moves.main() unchanged.
- plan-less commands (init, verify-handoff): pass through directly.
- unknown contract_version: refused with exit 1.
- no argv: delegated so argparse prints its usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from . import moves
except ImportError:
    import moves


SUPPORTED_VERSIONS = {"unconventional-moves/v0.1", "unconventional-moves/v0.2"}

# Commands that require a v0.2 plan (selected_move_id and experiment cards).
V02_REQUIRED_COMMANDS = frozenset({
    "card", "outcome", "select", "observation-draft", "handoff",
})

# Commands that accept either v0.1 or v0.2 plans at argv[1].
SHARED_COMMANDS = frozenset({
    "debrief", "table", "record", "review", "render", "screen", "sources",
    "limits", "timeline",
})

# Commands that take no plan argument and skip version detection.
NO_PLAN_COMMANDS = frozenset({"init", "verify-handoff"})


def detect_version(plan_path: Path) -> str | None:
    """Return the contract_version from a plan file, or None on parse error."""
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("contract_version")
    return value if isinstance(value, str) else None


def gate_version(command: str, argv: list[str]) -> int | None:
    """Return a non-zero exit code to refuse, or None to pass through."""
    if not argv:
        return None
    if command in NO_PLAN_COMMANDS:
        return None
    if command not in V02_REQUIRED_COMMANDS and command not in SHARED_COMMANDS:
        return None
    if len(argv) < 2:
        return None
    plan_path = Path(argv[1])
    if not plan_path.exists():
        return None
    version = detect_version(plan_path)
    if version is None:
        return None
    if version not in SUPPORTED_VERSIONS:
        print("FAIL unsupported contract_version: " + version, file=sys.stderr)
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