#!/usr/bin/env python3
"""Local authoring and review utilities. Never execute the proposed moves."""
from __future__ import annotations

import argparse
import html
import hashlib
import json
import math
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


def plan_digest(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def selected_move(plan: dict) -> dict:
    if plan["contract_version"] != "unconventional-moves/v0.2":
        raise ValueError("experiment workflow requires a version 0.2 plan")
    return next(move for move in plan["moves"] if move["id"] == plan["selected_move_id"])


def experiment_card(plan: dict) -> dict:
    move = selected_move(plan)
    return {"contract_version": "unconventional-moves/card-v0.1", "plan_sha256": plan_digest(plan),
            "state": "human_review_required", "goal": plan["goal"], "move_id": move["id"],
            "concrete_move": move["concrete_move"], "success_signal": move["success_signal"],
            "stop_condition": move["stop_condition"], "experiment": move["experiment"],
            "high_stakes": plan["high_stakes"],
            "review_before_start": ["Confirm actual consent and authority.", "Verify baseline and measurement method.",
                                    "Check current sources when high stakes.", "Confirm rollback and downside limits."],
            "limitation": "This card grants no authority and does not start, schedule, or execute a test."}


OUTCOME_FIELDS = {"contract_version", "plan_sha256", "move_id", "observed_value", "elapsed_hours", "active_minutes", "stop_triggered", "consent_confirmed", "notes"}


def evaluate_outcome(plan: dict, outcome: object) -> dict:
    move = selected_move(plan)
    if not isinstance(outcome, dict) or set(outcome) != OUTCOME_FIELDS:
        raise ValueError("outcome must contain exactly the documented fields")
    if outcome["contract_version"] != "unconventional-moves/outcome-v0.1":
        raise ValueError("unsupported outcome contract")
    if outcome["plan_sha256"] != plan_digest(plan) or outcome["move_id"] != move["id"]:
        raise ValueError("outcome does not match the current plan revision and selected move")
    for field in ("observed_value", "elapsed_hours", "active_minutes"):
        value = outcome[field]
        if value is None and field == "observed_value":
            continue
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            raise ValueError(f"outcome {field} must be finite numeric data")
        if field != "observed_value" and not 0 <= value <= 1_000_000:
            raise ValueError(f"outcome {field} must be between zero and one million")
    for field in ("stop_triggered", "consent_confirmed"):
        if type(outcome[field]) is not bool:
            raise ValueError(f"outcome {field} must be boolean")
    if not isinstance(outcome["notes"], str) or not outcome["notes"].strip():
        raise ValueError("outcome notes must describe the observation and limitations")
    if outcome["active_minutes"] > outcome["elapsed_hours"] * 60:
        raise ValueError("outcome active minutes cannot exceed elapsed time")
    experiment = move["experiment"]
    reasons = []
    if outcome["stop_triggered"]:
        reasons.append("declared_stop_condition_triggered")
    if outcome["active_minutes"] >= experiment["max_minutes"]:
        reasons.append("active_time_limit_reached")
    if outcome["elapsed_hours"] >= experiment["duration_hours"]:
        reasons.append("experiment_window_ended")
    if experiment["exposure"] == "consenting_participants" and not outcome["consent_confirmed"]:
        reasons.append("consent_not_confirmed")
    observed = outcome["observed_value"]
    target_met = None if observed is None else (observed >= experiment["target"] if experiment["direction"] == "increase" else observed <= experiment["target"])
    return {"plan_sha256": plan_digest(plan), "move_id": move["id"], "target_met": target_met,
            "decision": "stop_and_review" if reasons else "review_observation", "reasons": reasons,
            "source_verification_required": plan["high_stakes"],
            "limitation": "Self-reported observations do not establish causation or general effectiveness. No result authorizes continuation or expansion."}


def compare_plans(before: dict, after: dict) -> dict:
    old = {move["id"]: move for move in before["moves"]}
    new = {move["id"]: move for move in after["moves"]}
    changed = []
    for move_id in sorted(old.keys() & new.keys()):
        fields = []
        for field in sorted(old[move_id].keys() | new[move_id].keys()):
            left, right = old[move_id].get(field), new[move_id].get(field)
            if left != right:
                if field == "experiment" and isinstance(left, dict) and isinstance(right, dict):
                    fields.extend({"field": "experiment." + key, "before": left.get(key), "after": right.get(key)}
                                  for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key))
                else:
                    fields.append({"field": field, "before": left, "after": right})
        if fields:
            changed.append({"move_id": move_id, "changes": fields})
    metadata = [{"field": field, "before": before.get(field), "after": after.get(field)}
                for field in sorted((before.keys() | after.keys()) - {"moves"}) if before.get(field) != after.get(field)]
    return {"before_sha256": plan_digest(before), "after_sha256": plan_digest(after),
            "added_move_ids": sorted(new.keys() - old.keys()), "removed_move_ids": sorted(old.keys() - new.keys()),
            "move_order_changed": list(old) != list(new), "changed_moves": changed, "metadata_changes": metadata,
            "limitation": "A changed plan needs renewed review. Differences do not establish improvement."}


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
    card = commands.add_parser("card", help="Prepare a review-only card for the selected move")
    card.add_argument("plan", type=Path)
    card.add_argument("--output", type=Path)
    outcome = commands.add_parser("outcome", help="Compare reported observations with declared bounds")
    outcome.add_argument("plan", type=Path)
    outcome.add_argument("observation", type=Path)
    outcome.add_argument("--output", type=Path)
    compare = commands.add_parser("compare", help="Compare plan revisions using stable move IDs")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            plan = read_plan(ROOT / "examples/bounded-plan.json")
            emit(json.dumps(plan, indent=2) + "\n", args.output)
        elif args.command == "review":
            emit(json.dumps(review_plan(read_plan(args.plan)), indent=2) + "\n", args.output)
        elif args.command == "render":
            emit(render_plan(read_plan(args.plan)), args.output)
        elif args.command == "card":
            emit(json.dumps(experiment_card(read_plan(args.plan)), indent=2) + "\n", args.output)
        elif args.command == "outcome":
            result = evaluate_outcome(read_plan(args.plan), read_json_file(args.observation))
            emit(json.dumps(result, indent=2) + "\n", args.output)
        elif args.command == "compare":
            result = compare_plans(read_plan(args.before), read_plan(args.after))
            emit(json.dumps(result, indent=2) + "\n", args.output)
    except FileExistsError:
        print("FAIL output already exists; choose a new path", file=sys.stderr)
        return 1
    except (OSError, UnicodeError):
        print("FAIL input or output file is unavailable or not UTF-8", file=sys.stderr)
        return 1
    except json.JSONDecodeError:
        print("FAIL invalid JSON", file=sys.stderr)
        return 1
    except ValueError as exc:
        print("FAIL " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
