#!/usr/bin/env python3
"""Local authoring and review utilities. Never execute the proposed moves."""
from __future__ import annotations

import argparse
import csv
import io
import html
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from decimal import Decimal, localcontext
from datetime import date
from urllib.parse import urlsplit

try:
    from .validate_plan import MAX_PLAN_BYTES, read_json_file, validate_plan_data
except ImportError:
    from validate_plan import MAX_PLAN_BYTES, read_json_file, validate_plan_data

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


def render_html(plan: dict) -> str:
    def escape(value):
        return html.escape(str(value), quote=True)
    selected = plan.get("selected_move_id")
    sections, navigation = [], []
    for index, move in enumerate(plan["moves"], 1):
        anchor = "move-" + str(index)
        chosen = move["id"] == selected
        navigation.append(f'<a href="#{anchor}">{index:02d} {escape(move["title"])}' + (" (selected)" if chosen else "") + '</a>')
        fields = "".join(f'<dt>{escape(key.replace("_", " ").title())}</dt><dd>{escape(move[key])}</dd>'
                         for key in ("mechanism", "concrete_move", "why_overlooked", "test_48h", "success_signal", "stop_condition", "evidence_status", "bounds"))
        experiment = ""
        if "experiment" in move:
            rows = "".join(f'<dt>{escape(key.replace("_", " ").title())}</dt><dd>{escape(value)}</dd>' for key, value in move["experiment"].items())
            experiment = '<details open><summary>Declared experiment and rollback</summary><dl>' + rows + '</dl></details>'
        sections.append(f'<article id="{anchor}"><p class="eyebrow">Approach {index:02d}' + (" / Human-selected" if chosen else "") +
                        f'</p><h2>{escape(move["title"])}</h2><p class="identity">{escape(move["id"])}</p><dl>{fields}</dl>{experiment}<a class="back" href="#top">Back to overview</a></article>')
    sources = "".join('<li>' + escape(" | ".join(str(source[key]) for key in ("title", "publisher", "date", "url", "supports") if key in source)) + '</li>' for source in plan["sources"])
    css = '''body{margin:0;background:#f3f5f8;color:#172337;font:17px/1.6 system-ui,sans-serif}main{max-width:1060px;margin:auto;padding:40px 24px}h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.15;margin:12px 0}h2{font-size:1.6rem;line-height:1.25}h3{font-size:1.1rem}.eyebrow{font-size:.78rem;text-transform:uppercase;letter-spacing:.12em;font-weight:700;color:#35567b}.notice{border-left:4px solid #bd7c22;background:#fff5e1;padding:16px 20px}.identity{font:13px/1.6 ui-monospace,monospace;color:#526073;overflow-wrap:anywhere}nav{display:grid;gap:8px;margin:24px 0}a{color:#174d85;text-underline-offset:4px}nav a{padding:10px 14px;border:1px solid #cbd3df;background:white;border-radius:5px}a:focus-visible,summary:focus-visible{outline:3px solid #9b4e05;outline-offset:4px}article{background:white;border:1px solid #dce2ea;border-radius:10px;padding:28px;margin:24px 0;scroll-margin-top:16px}dl{display:grid;grid-template-columns:180px 1fr;gap:12px 20px}dt{font-weight:650}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;font-weight:700;padding:10px 0}details{border-top:1px solid #dce2ea;margin-top:22px}.back{display:inline-block;margin-top:18px}li{overflow-wrap:anywhere}footer{padding-top:20px;border-top:1px solid #cbd3df}section p{overflow-wrap:anywhere}@media(max-width:600px){main{padding:24px 16px}article{padding:20px}dl{grid-template-columns:1fr;gap:4px}dd{margin-bottom:14px}}@media print{body{background:white;font-size:11pt}main{max-width:none;padding:0}nav,.back{display:none}article{break-inside:avoid;border-radius:0}details{display:block}a{color:inherit}}'''
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>Unconventional Moves / Review</title><style>' + css + '</style></head><body><main id="top"><header><p class="eyebrow">Unconventional Moves / Offline review</p><h1>A considered next move.</h1><p>' + escape(plan["goal"]) + '</p><p class="identity">Plan SHA-256: ' + plan_digest(plan) + '</p><p class="notice"><strong>Human review required.</strong> No action is started or approved. Claims, consent, measurement, and rollback still need review.' + (' High-stakes plan: current reliable sources require human verification.' if plan["high_stakes"] else '') + '</p></header><nav aria-label="Approaches">' + ''.join(navigation) + '</nav><section aria-label="Recorded priority"><h2>Recorded priority</h2><p>' + escape(plan["prioritized_action"]) + '</p></section>' + ''.join(sections) + '<footer><h2>Declared sources</h2><p>No source was opened or verified by this report.</p><ul>' + (sources or '<li>None supplied.</li>') + '</ul><p>Comparison, novelty, safety, and effectiveness remain matters for human review. This offline report contains no execution or account controls.</p></footer></main></body></html>\n'


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


def render_card(plan: dict) -> str:
    card = experiment_card(plan)
    lines = ["# Experiment review card", "", "Human review required. No test has been started.", ""]
    for field in ("plan_sha256", "goal", "move_id", "concrete_move", "success_signal", "stop_condition", "high_stakes"):
        lines.append("- **" + field.replace("_", " ").title() + ":** " + markdown_text(str(card[field])))
    lines.extend(["", "## Declared experiment", ""])
    for field, value in card["experiment"].items():
        lines.append("- **" + field.replace("_", " ").title() + ":** " + markdown_text(str(value)))
    lines.extend(["", "## Review before starting", ""])
    lines.extend("- [ ] " + markdown_text(item) for item in card["review_before_start"])
    lines.extend(["", "**Recorded first step and reason:** " + markdown_text(plan["prioritized_action"]), "",
                  "Source claims: " + str(len(plan["sources"])) + " supplied; none verified by this card.", "", card["limitation"], ""])
    return "\n".join(lines)


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
    triggers = []
    for item in metadata:
        if item["field"] in {"selected_move_id", "high_stakes", "sources", "goal", "prioritized_action", "contract_version"}:
            triggers.append({"move_id": None, "field": item["field"], "reason": "review_context_changed"})
    for move in changed:
        for item in move["changes"]:
            field = item["field"]
            if field.startswith("experiment.") or field in {"concrete_move", "bounds", "stop_condition", "success_signal", "evidence_status"}:
                reason = "experiment_or_review_condition_changed"
                if field in {"experiment.max_minutes", "experiment.duration_hours", "experiment.start_within_hours"} and item["after"] > item["before"]:
                    reason = "declared_time_bound_expanded"
                triggers.append({"move_id": move["move_id"], "field": field, "reason": reason})
    for move_id in sorted(old.keys() ^ new.keys()):
        triggers.append({"move_id": move_id, "field": "move", "reason": "move_added_or_removed"})
    return {"before_sha256": plan_digest(before), "after_sha256": plan_digest(after),
            "added_move_ids": sorted(new.keys() - old.keys()), "removed_move_ids": sorted(old.keys() - new.keys()),
            "move_order_changed": list(old) != list(new), "changed_moves": changed, "metadata_changes": metadata,
            "review_triggers": triggers, "observation_binding_changed": plan_digest(before) != plan_digest(after),
            "limitation": "A changed plan needs renewed review. Differences do not establish improvement."}


def handoff_bundle(plan: dict, observation: object = None) -> dict:
    bundle = {"contract_version": "unconventional-moves/handoff-v0.1", "plan": plan,
              "plan_sha256": plan_digest(plan), "card": experiment_card(plan), "review": review_plan(plan),
              "observation": observation, "outcome_review": None if observation is None else evaluate_outcome(plan, observation)}
    if len((json.dumps(bundle, indent=2) + "\n").encode("utf-8")) > MAX_PLAN_BYTES:
        raise ValueError("handoff exceeds the supported JSON byte limit")
    return bundle


def verify_handoff(bundle: object) -> dict:
    fields = {"contract_version", "plan", "plan_sha256", "card", "review", "observation", "outcome_review"}
    if not isinstance(bundle, dict) or set(bundle) != fields or bundle["contract_version"] != "unconventional-moves/handoff-v0.1":
        raise ValueError("unsupported handoff structure")
    if validate_plan_data(bundle["plan"]):
        raise ValueError("handoff contains an invalid plan")
    expected = handoff_bundle(bundle["plan"], bundle["observation"])
    if json.dumps(bundle, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise ValueError("handoff digest or derived review does not match its contents")
    return {"consistent": True, "plan_sha256": expected["plan_sha256"], "move_id": expected["card"]["move_id"],
            "observation_present": bundle["observation"] is not None, "human_review_required": True,
            "limitation": "Internal consistency only. Unsigned local bundle; authorship, factual truth, consent, and approval are not authenticated."}


def screen_moves(plan: dict, max_minutes: int, exposure: str,
                 max_start_hours: int | None = None, max_duration_hours: int | None = None) -> dict:
    selected_move(plan)
    if type(max_minutes) is not int or not 1 <= max_minutes <= 2880:
        raise ValueError("maximum active minutes must be an integer from 1 to 2880")
    if exposure not in {"self_only", "consenting_participants"}:
        raise ValueError("unsupported exposure ceiling")
    for value, minimum in ((max_start_hours, 0), (max_duration_hours, 1)):
        if value is not None and (type(value) is not int or not minimum <= value <= 48):
            raise ValueError("start and duration ceilings must be integer hours within the supported 48-hour bounds")
    fits, excluded = [], []
    for move in plan["moves"]:
        experiment, reasons = move["experiment"], []
        if experiment["max_minutes"] > max_minutes:
            reasons.append("active_time_exceeds_ceiling")
        if exposure == "self_only" and experiment["exposure"] != "self_only":
            reasons.append("participants_outside_ceiling")
        if max_start_hours is not None and experiment["start_within_hours"] > max_start_hours:
            reasons.append("start_window_exceeds_ceiling")
        if max_duration_hours is not None and experiment["duration_hours"] > max_duration_hours:
            reasons.append("duration_exceeds_ceiling")
        if reasons:
            excluded.append({"move_id": move["id"], "reasons": reasons})
        else:
            fits.append(move["id"])
    return {"plan_sha256": plan_digest(plan), "max_minutes": max_minutes, "exposure_ceiling": exposure,
            "max_start_hours": max_start_hours, "max_duration_hours": max_duration_hours,
            "matching_move_ids": fits, "excluded": excluded, "selected_move_id": plan["selected_move_id"],
            "selected_within_constraints": plan["selected_move_id"] in fits,
            "limitation": "Original order retained. Declared constraints only; no ranking, consent verification, safety certification, or automatic selection."}


def iso_date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must use YYYY-MM-DD")
    return date.fromisoformat(value)


def audit_sources(plan: dict, as_of: str, max_age_days: int) -> dict:
    reference = iso_date(as_of)
    if type(max_age_days) is not int or not 0 <= max_age_days <= 36500:
        raise ValueError("max age must be an integer from 0 to 36500 days")
    sources, urls, publishers = [], {}, {}
    for index, source in enumerate(plan["sources"], 1):
        parsed = urlsplit(source["url"])
        url_key = parsed._replace(netloc=parsed.netloc.lower(), fragment="").geturl()
        urls.setdefault(url_key, []).append(index)
        publisher_key = " ".join(source.get("publisher", "").casefold().split())
        if publisher_key:
            publishers.setdefault(publisher_key, []).append(index)
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
            "repeated_url_groups": [indices for indices in urls.values() if len(indices) > 1],
            "shared_declared_publisher_groups": [indices for indices in publishers.values() if len(indices) > 1],
            "independence_review_required": any(len(indices) > 1 for indices in [*urls.values(), *publishers.values()]),
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
        if index > 1 and Decimal(str(minutes)) - Decimal(str(previous_minutes)) > (Decimal(str(hours)) - Decimal(str(previous_hours))) * 60:
            raise ValueError("checkpoint active-time increase exceeds the elapsed interval")
        stop_reasons.update(review["reasons"])
        if stop_reasons and first_stop is None:
            first_stop = index
        interval_hours = Decimal(str(hours)) - Decimal(str(max(0, previous_hours)))
        interval_minutes = Decimal(str(minutes)) - Decimal(str(max(0, previous_minutes)))
        checkpoints.append({"checkpoint": index, "elapsed_hours": hours, "active_minutes": minutes,
                            "interval_hours": str(interval_hours), "interval_active_minutes": str(interval_minutes),
                            "interval_activity_fraction": str(interval_minutes / (interval_hours * 60)) if interval_hours else None,
                            "review": review, "after_stop": first_stop is not None and index > first_stop})
        previous_hours, previous_minutes = hours, minutes
    measured = [row for row in checkpoints if row["review"]["target_met"] is not None]
    attained = [row["checkpoint"] for row in measured if row["review"]["target_met"]]
    first_target = attained[0] if attained else None
    lost = [row["checkpoint"] for row in measured
            if first_target is not None and row["checkpoint"] > first_target and not row["review"]["target_met"]]
    return {"plan_sha256": plan_digest(plan), "move_id": selected_move(plan)["id"],
            "measurement_summary": {"measured_checkpoints": len(measured),
                "missing_checkpoints": [row["checkpoint"] for row in checkpoints if row["review"]["target_met"] is None],
                "first_target_checkpoint": first_target, "target_lost_checkpoints": lost,
                "latest_checkpoint_target_met": checkpoints[-1]["review"]["target_met"],
                "first_target_after_stop": first_target is not None and first_stop is not None and first_target > first_stop},
            "checkpoints": checkpoints, "first_stop_checkpoint": first_stop,
            "decision": "stop_and_review" if stop_reasons else "review_observations",
            "reasons": sorted(stop_reasons), "observations_after_stop": first_stop is not None and first_stop < len(observations),
            "limitation": "Cumulative self-reports only. Earlier stop conditions remain active; later entries do not authorize continuation."}


def portfolio_rows(plan: dict) -> list[dict]:
    selected_move(plan)
    return [{"plan_sha256": plan_digest(plan), "move_id": move["id"], "title": move["title"],
             "selected": move["id"] == plan["selected_move_id"], "mechanism": move["mechanism"],
             **{key: move["experiment"][key] for key in ("metric", "baseline", "target", "direction",
                 "start_within_hours", "duration_hours", "max_minutes", "exposure", "rollback")},
             "review_state": "human_review_required"} for move in plan["moves"]]


def portfolio_csv(plan: dict) -> str:
    rows = portfolio_rows(plan)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    # Spreadsheet text markers keep authored cells inert, including multiline formulas.
    writer.writerows({key: "'" + value if isinstance(value, str) else value for key, value in row.items()} for row in rows)
    return output.getvalue()


def review_limits(plan: dict, observations: object) -> dict:
    timeline = review_timeline(plan, observations)
    experiment = selected_move(plan)["experiment"]
    latest = observations[-1]
    bounds = {}
    for reported, declared in (("elapsed_hours", "duration_hours"), ("active_minutes", "max_minutes")):
        consumed, maximum = Decimal(str(latest[reported])), Decimal(str(experiment[declared]))
        bounds[reported] = {"declared_limit": experiment[declared], "reported": latest[reported],
                            "remaining": str(max(Decimal(0), maximum - consumed)),
                            "overrun": str(max(Decimal(0), consumed - maximum)),
                            "limit_reached": consumed >= maximum}
    return {"plan_sha256": timeline["plan_sha256"], "move_id": timeline["move_id"], "bounds": bounds,
            "decision": timeline["decision"], "reasons": timeline["reasons"],
            "first_stop_checkpoint": timeline["first_stop_checkpoint"],
            "limitation": "Unused declared bounds are not permission to continue. Earlier stops, actual consent, and human authority still control."}


def append_checkpoint(plan: dict, observation: object, history: object = None) -> list:
    if history is not None and not isinstance(history, list):
        raise ValueError("checkpoint history must be an array")
    observations = [*(history or []), observation]
    review_timeline(plan, observations)
    if len((json.dumps(observations, indent=2) + "\n").encode("utf-8")) > MAX_PLAN_BYTES:
        raise ValueError("checkpoint history exceeds the supported JSON byte limit")
    return observations


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
    if len((json.dumps(revised, indent=2) + "\n").encode("utf-8")) > MAX_PLAN_BYTES:
        raise ValueError("selected revision exceeds the supported JSON byte limit")
    return revised


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    table = commands.add_parser("table", help="Export comparable declared experiment rows without ranking")
    table.add_argument("plan", type=Path)
    table.add_argument("--format", choices=["json", "csv"], default="json")
    table.add_argument("--output", type=Path)
    record = commands.add_parser("record", help="Append an observation to a new validated checkpoint file")
    record.add_argument("plan", type=Path)
    record.add_argument("observation", type=Path)
    record.add_argument("--history", type=Path)
    record.add_argument("--output", type=Path, required=True)
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
    limits = commands.add_parser("limits", help="Review remaining bounds and overruns across checkpoint history")
    limits.add_argument("plan", type=Path)
    limits.add_argument("observations", type=Path)
    limits.add_argument("--output", type=Path)
    sources = commands.add_parser("sources", help="Audit declared source dates without network access")
    sources.add_argument("plan", type=Path)
    sources.add_argument("--as-of", required=True)
    sources.add_argument("--max-age-days", type=int, required=True)
    sources.add_argument("--output", type=Path)
    screen = commands.add_parser("screen", help="Shortlist declared bounds without ranking or selecting moves")
    screen.add_argument("plan", type=Path)
    screen.add_argument("--max-minutes", type=int, required=True)
    screen.add_argument("--exposure", choices=["self_only", "consenting_participants"], required=True)
    screen.add_argument("--max-start-hours", type=int)
    screen.add_argument("--max-duration-hours", type=int)
    screen.add_argument("--output", type=Path)
    handoff = commands.add_parser("handoff", help="Bundle the plan and derived review for offline handoff")
    handoff.add_argument("plan", type=Path)
    handoff.add_argument("--observation", type=Path)
    handoff.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-handoff", help="Recompute a handoff's internal consistency")
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--output", type=Path)
    review = commands.add_parser("review", help="Inspect mechanism diversity and evidence labels")
    review.add_argument("plan", type=Path)
    review.add_argument("--output", type=Path)
    render = commands.add_parser("render", help="Render a validated plan as inert Markdown")
    render.add_argument("plan", type=Path)
    render.add_argument("--format", choices=["markdown", "html"], default="markdown")
    render.add_argument("--output", type=Path)
    card = commands.add_parser("card", help="Prepare a review-only card for the selected move")
    card.add_argument("plan", type=Path)
    card.add_argument("--format", choices=["json", "markdown"], default="json")
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
        if args.command == "table":
            plan = read_plan(args.plan)
            emit(portfolio_csv(plan) if args.format == "csv" else json.dumps(portfolio_rows(plan), indent=2) + "\n", args.output)
        elif args.command == "record":
            result = append_checkpoint(read_plan(args.plan), read_json_file(args.observation),
                                       read_json_file(args.history) if args.history else None)
            emit(json.dumps(result, indent=2) + "\n", args.output)
        elif args.command == "init":
            plan = read_plan(ROOT / "examples/bounded-plan.json")
            emit(json.dumps(plan, indent=2) + "\n", args.output)
        elif args.command == "handoff":
            result = handoff_bundle(read_plan(args.plan), read_json_file(args.observation) if args.observation else None)
            emit(json.dumps(result, indent=2) + "\n", args.output)
        elif args.command == "verify-handoff":
            emit(json.dumps(verify_handoff(read_json_file(args.bundle)), indent=2) + "\n", args.output)
        elif args.command == "screen":
            result = screen_moves(read_plan(args.plan), args.max_minutes, args.exposure,
                                  args.max_start_hours, args.max_duration_hours)
            emit(json.dumps(result, indent=2) + "\n", args.output)
        elif args.command == "sources":
            result = audit_sources(read_plan(args.plan), args.as_of, args.max_age_days)
            emit(json.dumps(result, indent=2) + "\n", args.output)
        elif args.command == "limits":
            result = review_limits(read_plan(args.plan), read_json_file(args.observations))
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
            plan = read_plan(args.plan)
            emit(render_html(plan) if args.format == "html" else render_plan(plan), args.output)
        elif args.command == "card":
            plan = read_plan(args.plan)
            emit(render_card(plan) if args.format == "markdown" else json.dumps(experiment_card(plan), indent=2) + "\n", args.output)
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
