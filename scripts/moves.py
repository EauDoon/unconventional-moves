#!/usr/bin/env python3
"""Local authoring and review utilities. Never execute the proposed moves."""
from __future__ import annotations

import argparse
import html
import json
import re
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


def review_plan(plan: dict) -> dict:
    """Deterministic editorial prompts, not a safety or novelty certification."""
    findings = []
    for field in ("mechanism", "concrete_move", "test_48h"):
        seen = {}
        for move in plan["moves"]:
            normalized = " ".join(move[field].casefold().split())
            if normalized in seen:
                findings.append({"code": "repeated_" + field, "move_id": move["id"],
                                 "related_move_id": seen[normalized],
                                 "message": "Review whether these moves provide distinct learning."})
            else:
                seen[normalized] = move["id"]
    for move in plan["moves"]:
        if not re.search(r"(?i)\b(fact|source|prompt|inferen\w*|speculat\w*|hypothes\w*|assum\w*)\b", move["evidence_status"]):
            findings.append({"code": "evidence_label_unclear", "move_id": move["id"],
                             "message": "Separate supported facts from inference and speculation."})
    if plan["high_stakes"]:
        findings.append({"code": "source_verification_required", "message":
                         "A human must verify source currency, authority, relevance, and consequential boundaries before proceeding."})
    if plan["contract_version"].endswith("v0.1"):
        findings.append({"code": "unstructured_bounds", "message": "Version 0.1 bounds require manual review; version 0.2 adds measurable fields."})
    return {"contract_valid": True, "review_complete": False, "findings": findings,
            "human_checks": ["Do the mechanisms differ in practice?", "Are costs, consent, and rollback realistic?",
                             "Does the success signal measure the goal?", "Does one selected action follow from the stated constraints?"],
            "limitation": "Text checks cannot establish novelty, truth, safety, consent, or likely effectiveness."}


def markdown_text(value: object) -> str:
    """Render user text as a single inert Markdown paragraph."""
    text = " ".join(str(value).split())
    text = re.sub(r"([\\`*_{}\[\]()#+.!|>~:-])", r"\\\1", text)
    return html.escape(text, quote=False)


def render_plan(plan: dict) -> str:
    lines = ["# Unconventional Moves plan", "", markdown_text(plan["goal"]), "",
             "Declared plan only. Human review is required before any experiment.", ""]
    for move in plan["moves"]:
        lines.extend(["## " + markdown_text(move["id"]) + ": " + markdown_text(move["title"]), ""])
        for field in ("mechanism", "concrete_move", "why_overlooked", "test_48h", "success_signal", "stop_condition", "evidence_status", "bounds"):
            lines.extend(["**" + field.replace("_", " ").capitalize() + ":** " + markdown_text(move[field]), ""])
        if "experiment" in move:
            for field, value in move["experiment"].items():
                lines.extend(["**Experiment " + field.replace("_", " ") + ":** " + markdown_text(value), ""])
    lines.extend(["**Prioritized action:** " + markdown_text(plan["prioritized_action"]), "", "## Sources", ""])
    if not plan["sources"]:
        lines.extend(["None supplied. This is not verification of factual claims.", ""])
    for source in plan["sources"]:
        lines.extend(["- " + " | ".join(markdown_text(source[field]) for field in ("title", "publisher", "date", "url", "supports") if field in source)])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Copy a complete synthetic language-practice plan for editing")
    init.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("review", help="Inspect mechanism diversity and evidence labels")
    review.add_argument("plan", type=Path)
    review.add_argument("--output", type=Path)
    render = commands.add_parser("render", help="Render a validated plan as inert Markdown")
    render.add_argument("plan", type=Path)
    render.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            plan = read_plan(ROOT / "examples/bounded-plan.json")
            emit(json.dumps(plan, indent=2) + "\n", args.output)
        elif args.command == "review":
            emit(json.dumps(review_plan(read_plan(args.plan)), indent=2) + "\n", args.output)
        elif args.command == "render":
            emit(render_plan(read_plan(args.plan)), args.output)
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
