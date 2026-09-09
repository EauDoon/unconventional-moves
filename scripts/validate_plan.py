#!/usr/bin/env python3
"""Validate a machine-readable Unconventional Moves plan."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


MOVE_FIELDS = [
    "id",
    "title",
    "mechanism",
    "concrete_move",
    "why_overlooked",
    "test_48h",
    "success_signal",
    "stop_condition",
    "evidence_status",
    "bounds",
]
UNSAFE = re.compile(
    r"(?i)\b(?:bypass(?:es|ed|ing)?\s+(?:(?:a|the)\s+)?safety|"
    r"steal(?:s|ing)?|stole|stolen|harass\w*|"
    r"disabl(?:e|es|ed|ing)\s+(?:the\s+)?safety|"
    r"ignor(?:e|es|ed|ing)\s+(?:the\s+)?(?:consent|scope|safety)|exfiltrat\w*|"
    r"evad(?:e|es|ed|ing)\s+(?:the\s+)?(?:law|consent))\b"
)
MAX_PLAN_BYTES = 1_000_000
TOP_LEVEL_FIELDS = {"contract_version", "goal", "high_stakes", "moves", "prioritized_action", "sources"}
SOURCE_FIELDS = {"title", "publisher", "date", "url", "supports"}


def _valid_source_url(value: str) -> bool:
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
        and bool(parsed.hostname)
        and "%" not in parsed.hostname
        and "\\" not in parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65535)
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def load_plan_json(raw: str) -> object:
    if not isinstance(raw, str):
        raise ValueError("JSON input must be text")
    if len(raw.encode("utf-8")) > MAX_PLAN_BYTES:
        raise ValueError(f"plan exceeds {MAX_PLAN_BYTES} bytes")
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc


def read_json_file(path: Path) -> object:
    """Bound the read itself, including files that grow after opening."""
    with path.open("rb") as handle:
        raw = handle.read(MAX_PLAN_BYTES + 1)
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError(f"plan exceeds {MAX_PLAN_BYTES} bytes")
    return load_plan_json(raw.decode("utf-8"))


EXPERIMENT_FIELDS = {"hypothesis", "metric", "baseline", "target", "direction", "start_within_hours", "duration_hours", "max_minutes", "exposure", "rollback"}


def validate_experiment(value: object, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} experiment must be an object"]
    failures = []
    if set(value) != EXPERIMENT_FIELDS:
        failures.append(f"{label} experiment must contain exactly the documented fields")
    for field in ("hypothesis", "metric", "rollback"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            failures.append(f"{label} experiment {field} must be non-empty text")
    for field in ("baseline", "target"):
        number = value.get(field)
        if type(number) not in (int, float) or (type(number) is float and not math.isfinite(number)):
            failures.append(f"{label} experiment {field} must be a finite number")
    for field, minimum, maximum in (("start_within_hours", 0, 48), ("duration_hours", 1, 48), ("max_minutes", 1, 2880)):
        number = value.get(field)
        if type(number) is not int or not minimum <= number <= maximum:
            failures.append(f"{label} experiment {field} must be an integer from {minimum} to {maximum}")
    if value.get("direction") not in ("increase", "decrease"):
        failures.append(f"{label} experiment direction must be increase or decrease")
    if value.get("exposure") not in ("self_only", "consenting_participants"):
        failures.append(f"{label} experiment exposure must be self_only or consenting_participants")
    if not failures:
        if (value["target"] <= value["baseline"] if value["direction"] == "increase" else value["target"] >= value["baseline"]):
            failures.append(f"{label} experiment target must improve on baseline in the stated direction")
        if value["max_minutes"] > value["duration_hours"] * 60:
            failures.append(f"{label} experiment max_minutes exceeds duration")
    return failures


def validate_plan_data(data: object, raw: str = "") -> list[str]:
    failures: list[str] = []
    if not isinstance(data, dict):
        return ["plan must be a JSON object"]
    v2 = data.get("contract_version") == "unconventional-moves/v0.2"
    unknown_top = sorted(set(data) - (TOP_LEVEL_FIELDS | ({"selected_move_id"} if v2 else set())))
    if unknown_top:
        failures.append(f"plan has unknown fields: {', '.join(unknown_top)}")
    if data.get("contract_version") not in ("unconventional-moves/v0.1", "unconventional-moves/v0.2"):
        failures.append("contract_version must be unconventional-moves/v0.1 or unconventional-moves/v0.2")
    if not isinstance(data.get("goal"), str) or not data["goal"].strip():
        failures.append("goal must be a non-empty string")
    moves = data.get("moves")
    if not isinstance(moves, list) or not 5 <= len(moves) <= 7:
        failures.append("moves must contain five to seven entries")
        moves = []
    ids: list[str] = []
    for index, move in enumerate(moves, 1):
        if not isinstance(move, dict):
            failures.append(f"move {index} must be an object")
            continue
        unknown_move = sorted(set(move) - (set(MOVE_FIELDS) | ({"experiment"} if v2 else set())))
        if unknown_move:
            failures.append(f"move {index} has unknown fields: {', '.join(unknown_move)}")
        missing = [field for field in MOVE_FIELDS if not isinstance(move.get(field), str) or not move[field].strip()]
        if missing:
            failures.append(f"move {index} missing non-empty fields: {', '.join(missing)}")
        if v2:
            failures.extend(validate_experiment(move.get("experiment"), f"move {index}"))
        move_id = move.get("id")
        if isinstance(move_id, str):
            ids.append(move_id)
        for field in ("concrete_move", "test_48h", "success_signal", "stop_condition"):
            value = move.get(field, "")
            if isinstance(value, str) and UNSAFE.search(value):
                failures.append(f"move {index} contains an unsafe action in {field}")
    if len(ids) != len(set(ids)):
        failures.append("move IDs must be unique")

    if v2 and (not isinstance(data.get("selected_move_id"), str) or data["selected_move_id"] not in ids):
        failures.append("selected_move_id must identify exactly one existing move")

    prioritized = data.get("prioritized_action")
    if not isinstance(prioritized, str) or not prioritized.strip():
        failures.append("prioritized_action must be one non-empty string")
    elif UNSAFE.search(prioritized):
        failures.append("prioritized_action contains an unsafe action")
    sources = data.get("sources")
    if not isinstance(sources, list):
        failures.append("sources must be an array")
        sources = []
    for index, source in enumerate(sources, 1):
        if not isinstance(source, dict):
            failures.append(f"source {index} must be an object")
            continue
        unknown_source = sorted(set(source) - SOURCE_FIELDS)
        if unknown_source:
            failures.append(f"source {index} has unknown fields: {', '.join(unknown_source)}")
        for field in ("title", "url", "supports"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                failures.append(f"source {index} missing non-empty {field}")
        for field in ("publisher", "date"):
            if field in source and not isinstance(source[field], str):
                failures.append(f"source {index} {field} must be a string")
        if isinstance(source.get("url"), str) and not _valid_source_url(source["url"]):
            failures.append(f"source {index} URL must use http or https")
    if data.get("high_stakes") is True and not sources:
        failures.append("high-stakes plan requires at least one current source")
    if not isinstance(data.get("high_stakes"), bool):
        failures.append("high_stakes must be boolean")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        data = read_json_file(args.plan)
        failures = validate_plan_data(data)
    except OSError:
        failures = ["plan file cannot be read"]
    except UnicodeDecodeError:
        failures = ["plan must be UTF-8 JSON"]
    except ValueError as exc:
        failures = [str(exc) if str(exc) == "JSON object contains a duplicate key" else "invalid JSON or input exceeds supported bounds"]
    if args.as_json:
        print(json.dumps({"ok": not failures, "failures": failures}, sort_keys=True))
        return int(bool(failures))
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print(f"PASS valid plan: {args.plan}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
