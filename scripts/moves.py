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
from decimal import Decimal, localcontext
from datetime import date

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
            "measurement": measurement_context(experiment, observed),
            "decision": "stop_and_review" if reasons else "review_observation", "reasons": reasons,
            "source_verification_required": plan["high_stakes"],
            "limitation": "Self-reported observations do not establish causation or general effectiveness. No result authorizes continuation or expansion."}


def measurement_context(experiment: dict, observed: int | float | None) -> dict:
    result = {key: experiment[key] for key in ("metric", "baseline", "target", "direction")}
    result.update(observed_value=observed, change_from_baseline=None, progress_fraction=None)
    if observed is not None:
        with localcontext() as context:
            context.prec = 28
            baseline, target, value = (Decimal(str(number)) for number in
                                       (experiment["baseline"], experiment["target"], observed))
            result["change_from_baseline"] = str(value - baseline)
            result["progress_fraction"] = str((value - baseline) / (target - baseline))
    return result


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


def iso_date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must use YYYY-MM-DD")
    return date.fromisoformat(value)


def audit_sources(plan: dict, as_of: str, max_age_days: int) -> dict:
    reference = iso_date(as_of)
    if type(max_age_days) is not int or not 0 <= max_age_days <= 36500:
        raise ValueError("max age must be an integer from 0 to 36500 days")
    sources = []
    for index, source in enumerate(plan["sources"], 1):
        declared = source.get("date", "")
        age, status = None, "date_missing"
        if declared:
            try:
                age = (reference - iso_date(declared)).days
                status = "future_date" if age < 0 else "older_than_threshold" if age > max_age_days else "within_declared_threshold"
            except ValueError:
                status = "date_invalid"
        sources.append({"source": index, "title": source["title"], "declared_date": declared or None,
                        "age_days": age, "status": status})
    return {"plan_sha256": plan_digest(plan), "as_of": as_of, "max_age_days": max_age_days,
            "sources": sources, "sources_absent": not sources, "human_verification_required": True,
            "limitation": "Dates are user-declared. No URL was opened and no publisher, claim, relevance, or actual currency was verified."}


def review_timeline(plan: dict, observations: object) -> dict:
    if not isinstance(observations, list) or not 1 <= len(observations) <= 100:
        raise ValueError("timeline requires 1 to 100 cumulative observations")
    checkpoints, stop_reasons = [], set()
    previous_hours, previous_minutes, first_stop = -1, -1, None
    for index, observation in enumerate(observations, 1):
        review = evaluate_outcome(plan, observation)
        hours, minutes = observation["elapsed_hours"], observation["active_minutes"]
        if hours <= previous_hours or minutes < previous_minutes:
            raise ValueError("timeline requires increasing elapsed hours and nondecreasing cumulative active minutes")
        stop_reasons.update(review["reasons"])
        if stop_reasons and first_stop is None:
            first_stop = index
        checkpoints.append({"checkpoint": index, "elapsed_hours": hours, "active_minutes": minutes,
                            "review": review, "after_stop": first_stop is not None and index > first_stop})
        previous_hours, previous_minutes = hours, minutes
    return {"plan_sha256": plan_digest(plan), "move_id": selected_move(plan)["id"],
            "checkpoints": checkpoints, "first_stop_checkpoint": first_stop,
            "decision": "stop_and_review" if stop_reasons else "review_observations",
            "reasons": sorted(stop_reasons), "observations_after_stop": first_stop is not None and first_stop < len(observations),
            "limitation": "Cumulative self-reports only. Earlier stop conditions remain active; later entries do not authorize continuation."}


def observation_draft(plan: dict) -> dict:
    move = selected_move(plan)
    return {"contract_version": "unconventional-moves/outcome-v0.1",
            "plan_sha256": plan_digest(plan), "move_id": move["id"],
            "observed_value": None, "elapsed_hours": 0, "active_minutes": 0,
            "stop_triggered": False, "consent_confirmed": False, "notes": ""}


def select_plan(plan: dict, move_id: str, reason: str, first_step: str) -> dict:
    selected_move(plan)
    if move_id not in {move["id"] for move in plan["moves"]}:
        raise ValueError("move ID must identify an existing move")
    if not reason.strip() or not first_step.strip():
        raise ValueError("selection reason and first step must be non-empty")
    revised = json.loads(json.dumps(plan))
    revised["selected_move_id"] = move_id
    revised["prioritized_action"] = f"Selected {move_id}. Reason: {reason.strip()} First step: {first_step.strip()}"
    failures = validate_plan_data(revised)
    if failures:
        raise ValueError("; ".join(failures))
    return revised


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Copy a complete synthetic language-practice plan for editing")
    init.add_argument("--output", type=Path, required=True)
    select = commands.add_parser("select", help="Record a human choice and first step in a new revision")
    select.add_argument("plan", type=Path)
    select.add_argument("--move-id", required=True)
    select.add_argument("--reason", required=True)
    select.add_argument("--first-step", required=True)
    select.add_argument("--output", type=Path, required=True)
    draft = commands.add_parser("observation-draft", help="Prepare an unfilled observation bound to this revision")
    draft.add_argument("plan", type=Path)
    draft.add_argument("--output", type=Path, required=True)
    timeline = commands.add_parser("timeline", help="Review cumulative checkpoints with persistent stop conditions")
    timeline.add_argument("plan", type=Path)
    timeline.add_argument("observations", type=Path)
    timeline.add_argument("--output", type=Path)
    sources = commands.add_parser("sources", help="Audit declared source dates without network access")
    sources.add_argument("plan", type=Path)
    sources.add_argument("--as-of", required=True)
    sources.add_argument("--max-age-days", type=int, required=True)
    sources.add_argument("--output", type=Path)
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
        elif args.command == "sources":
            result = audit_sources(read_plan(args.plan), args.as_of, args.max_age_days)
            emit(json.dumps(result, indent=2) + "\n", args.output)
        elif args.command == "timeline":
            result = review_timeline(read_plan(args.plan), read_json_file(args.observations))
            emit(json.dumps(result, indent=2) + "\n", args.output)
        elif args.command == "observation-draft":
            emit(json.dumps(observation_draft(read_plan(args.plan)), indent=2) + "\n", args.output)
        elif args.command == "select":
            result = select_plan(read_plan(args.plan), args.move_id, args.reason, args.first_step)
            emit(json.dumps(result, indent=2) + "\n", args.output)
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
