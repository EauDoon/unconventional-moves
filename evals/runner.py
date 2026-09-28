"""Offline scenarios runner for the unconventional-moves behavior suite.

Reads each per-case JSON file under evals/cases/ and asserts its contents
against the structural and trigger rules documented in evals/rubric.md and
evals/cases.json. Prints PASS or FAIL per case with the failing reason.
Exits 0 when every case passes, 1 when any case fails, 2 when the suite shape
itself is wrong (wrong count, missing coverage, etc.).

This runner does not execute a model. It only checks that each declared case
matches the rubric's documented gates and judgments. It is intentionally
limited: it cannot establish semantic quality or correct invocation routing.

Usage from the repo root:

    python evals/runner.py

The runner accepts no flags. The behavior suite is fixed; tuning the rubric
or cases requires editing the source files and re-running this script.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases"
RUBRIC_PATH = ROOT / "evals" / "rubric.md"
SUITE_SOURCE = ROOT / "evals" / "cases.json"

REQUIRED_FIELDS = {
    "id",
    "split",
    "domain",
    "tags",
    "expected",
    "prompt",
    "review_notes",
}
VALID_EXPECTED = {
    "apply",
    "do_not_apply",
    "clarify_or_apply",
    "clarify_or_limit",
    "limit",
    "apply_v01_or_clarify",
    "refuse_or_redirect",
}
VALID_SPLITS = {"development", "held_out"}
VALID_DOMAINS = {
    "partnership_activation",
    "product_adoption",
    "distribution",
    "operational_efficiency",
    "personal_learning",
}
# Every declared contract must name a schema that actually ships, or the case
# asks a generator for output no validator in this repository can check.
CONTRACT_TAGS = {
    "unconventional-moves/v0.1": "json_v01",
    "unconventional-moves/v0.2": "json_v02",
}
DECLARED_COVERAGE_TAGS = {
    "explicit_invocation",
    "implicit_invocation",
    "negative_trigger",
    "vague_brief",
    "tight_budget",
    "conflicting_constraints",
    "near_duplicates",
    "unavailable_sources",
    "missing_numeric_baselines",
    "prompt_injection",
    "unsafe_objective",
    "json_v01",
    "json_v02",
}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EXPECTED_TO_GATES = {
    "apply": ("apply",),
    "do_not_apply": ("do not apply",),
    "clarify_or_apply": ("clarify", "apply"),
    "clarify_or_limit": ("clarify", "limit"),
    "limit": ("limit",),
    "apply_v01_or_clarify": ("apply", "clarify"),
    "refuse_or_redirect": ("refuse",),
}
SAFETY_EXPECTED = {"refuse_or_redirect"}
SAFETY_TAGS = {"unsafe_objective"}


def fail(reason: str) -> None:
    raise ValueError(reason)


def load_fixture_json(text: str) -> object:
    """Load fixture JSON and reject duplicate keys instead of keeping the last one."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("JSON object contains a duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=unique_object)
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc


def check_case(case: dict, rubric_text: str) -> None:
    missing = REQUIRED_FIELDS - set(case)
    if missing:
        fail(f"missing required fields: {sorted(missing)}")
    extra = set(case) - REQUIRED_FIELDS - {"json_contract"}
    if extra:
        fail(f"unexpected fields: {sorted(extra)}")
    case_id = case["id"]
    if not isinstance(case_id, str) or not case_id:
        fail("id must be a non-empty string")
    if not ID_PATTERN.match(case_id):
        fail(f"id '{case_id}' must match {ID_PATTERN.pattern}")
    for field in REQUIRED_FIELDS - {"tags"}:
        value = case[field]
        if not isinstance(value, str) or not value.strip():
            fail(f"{field} must be a non-empty string")
    tags = case["tags"]
    if not isinstance(tags, list) or not tags:
        fail("tags must be a non-empty list")
    if len(tags) != len(set(tags)):
        fail("tags must be unique within a case")
    for tag in tags:
        if not isinstance(tag, str) or not tag:
            fail("each tag must be a non-empty string")
    bad_tags = {tag for tag in tags if not isinstance(tag, str) or not tag}
    if bad_tags:
        fail(f"malformed tag(s): {sorted(bad_tags)}")
    if case["split"] not in VALID_SPLITS:
        fail(f"split '{case['split']}' not in {sorted(VALID_SPLITS)}")
    if case["expected"] not in VALID_EXPECTED:
        fail(f"expected '{case['expected']}' not in {sorted(VALID_EXPECTED)}")
    if case["domain"] not in VALID_DOMAINS:
        fail(f"domain '{case['domain']}' not in {sorted(VALID_DOMAINS)}")
    gate_phrases = EXPECTED_TO_GATES[case["expected"]]
    rubric_lower = rubric_text.lower()
    for phrase in gate_phrases:
        if phrase not in rubric_lower:
            fail(f"rubric does not document gate phrase '{phrase}' for '{case['expected']}'")
    if case["expected"] in SAFETY_EXPECTED and "unsafe" not in tags and "unsafe_objective" not in tags:
        fail(f"refuse_or_redirect cases must carry safety tag; got {sorted(tags)}")
    if "unsafe_objective" in tags and case["expected"] not in SAFETY_EXPECTED:
        fail("unsafe_objective tag requires expected in {'refuse_or_redirect'}")
    if "json_contract" in case:
        contract = case["json_contract"]
        if not isinstance(contract, str) or contract not in CONTRACT_TAGS:
            fail(f"json_contract {contract} must name a bundled contract version: {sorted(CONTRACT_TAGS)}")
        if CONTRACT_TAGS[contract] not in tags:
            fail(f"json_contract {contract} requires {CONTRACT_TAGS[contract]} tag")
    if "json_v01" in tags and case["expected"] == "apply_v01_or_clarify":
        if "missing_numeric_baselines" not in tags and "json_contract" not in case:
            fail("apply_v01_or_clarify expects missing_numeric_baselines tag")


def check_suite(cases: list[dict]) -> list[str]:
    problems: list[str] = []
    if len(cases) != 20:
        problems.append(f"suite must contain 20 cases; found {len(cases)}")
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids):
        problems.append("case ids must be unique across the suite")
    seen_splits: dict[str, set[str]] = {"development": set(), "held_out": set()}
    for case in cases:
        seen_splits[case["split"]].add(case["domain"])
    for split, domains in seen_splits.items():
        if domains != VALID_DOMAINS:
            problems.append(
                f"{split} split must cover all domains; missing {sorted(VALID_DOMAINS - domains)}"
            )
    held_out = [case for case in cases if case["split"] == "held_out"]
    if len(held_out) != 5:
        problems.append(f"held_out split must contain 5 cases; found {len(held_out)}")
    held_out_ids = [case["id"] for case in held_out]
    bad_prefix = [case_id for case_id in held_out_ids if not case_id.startswith("heldout-")]
    if bad_prefix:
        problems.append(f"held_out ids must start with 'heldout-'; got {bad_prefix}")
    covered_tags = {tag for case in cases for tag in case["tags"]}
    missing_tags = DECLARED_COVERAGE_TAGS - covered_tags
    if missing_tags:
        problems.append(f"missing declared tag coverage: {sorted(missing_tags)}")
    problems.extend(check_declared_suite(cases))
    return problems


def check_declared_suite(cases: list[dict]) -> list[str]:
    """Bind the inspected fixtures to the suite that results.json was scored from.

    The per-case files and evals/cases.json hold the same twenty cases. The
    recorded session probe was generated from the declared suite, so a fixture
    that has drifted away from it is not the case that produced the scores.
    """
    try:
        declared = load_fixture_json(SUITE_SOURCE.read_text(encoding="utf-8"))["cases"]
        expected = {case["id"]: case for case in declared}
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        return [f"declared suite cannot be read: {exc}"]
    inspected = {case["id"]: case for case in cases}
    problems = [
        f"case file and declared suite disagree on {case_id!r}"
        for case_id in sorted(set(inspected) ^ set(expected))
    ]
    problems.extend(
        f"case file {case_id!r} does not match its declared suite entry"
        for case_id in sorted(set(inspected) & set(expected))
        if inspected[case_id] != expected[case_id]
    )
    return problems


def main() -> int:
    if not CASES_DIR.is_dir():
        print(f"cases directory missing: {CASES_DIR}", file=sys.stderr)
        return 2
    rubric_text = RUBRIC_PATH.read_text(encoding="utf-8")
    case_paths = sorted(CASES_DIR.glob("*.json"))
    cases: list[dict] = []
    failures = 0
    for path in case_paths:
        try:
            case = load_fixture_json(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"FAIL  {path.stem}  invalid JSON: {exc}")
            failures += 1
            continue
        except ValueError as exc:
            print(f"FAIL  {path.stem}  {exc}")
            failures += 1
            continue
        try:
            check_case(case, rubric_text)
        except ValueError as exc:
            print(f"FAIL  {case.get('id', path.stem)}  {exc}")
            failures += 1
            continue
        print(f"PASS  {case['id']}")
        cases.append(case)
    suite_problems = check_suite(cases)
    print("")
    print(f"suite: {len(cases)} case files inspected")
    for problem in suite_problems:
        print(f"suite FAIL  {problem}")
    if failures:
        return 1
    if suite_problems:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())