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
    if case.get("json_contract") == "unconventional-moves/v0.1" and "json_v01" not in tags:
        fail("json_contract v0.1 requires json_v01 tag")
    if case.get("json_contract") == "unconventional-moves/v0.2" and "json_v02" not in tags:
        fail("json_contract v0.2 requires json_v02 tag")
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
            case = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"FAIL  {path.stem}  invalid JSON: {exc}")
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
    if failures or suite_problems:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())