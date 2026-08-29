#!/usr/bin/env python3
"""Dependency-light repository checks for Unconventional Moves."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from validate_plan import load_plan_json, validate_plan_data


LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
UNSAFE_STRUCTURE = re.compile(r"(?i)\b(?:ignore\s+(?:consent|scope|safety)|disable\s+safety|exfiltrat\w*)\b")


class Checker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.failures: list[str] = []
        self.checks: list[str] = []

    def ok(self, condition: bool, message: str) -> None:
        if condition:
            self.checks.append(message)
        else:
            self.failures.append(message)

    def read(self, relative: str) -> str:
        path = self.root / relative
        self.ok(path.is_file(), f"file exists: {relative}")
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def json_file(self, relative: str) -> object:
        try:
            value = json.loads(self.read(relative))
            self.checks.append(f"valid JSON: {relative}")
            return value
        except (json.JSONDecodeError, OSError) as exc:
            self.failures.append(f"invalid JSON {relative}: {exc}")
            return None

    def check_links(self) -> None:
        for path in sorted(self.root.rglob("*.md")):
            if ".git" in path.parts or "dist" in path.parts:
                continue
            for raw in LINK.findall(path.read_text(encoding="utf-8")):
                target = raw.strip().split()[0].strip("<>")
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                relative = target.split("#", 1)[0]
                if not relative:
                    continue
                candidate = (path.parent / relative).resolve()
                self.ok(candidate.exists(), f"link exists: {path.relative_to(self.root)} -> {target}")

    def run(self) -> None:
        skill = self.read("skill/unconventional-moves/SKILL.md")
        readme = self.read("README.md")
        yaml = self.read("skill/unconventional-moves/agents/openai.yaml")
        self.ok(skill.startswith("\n---") or skill.startswith("---"), "SKILL.md has frontmatter")
        self.ok("name: unconventional-moves" in skill, "frontmatter keeps technical skill identifier")
        self.ok("## Sources" in skill, "skill has explicit Sources section")
        self.ok(len(re.findall(r"^\*\*Prioritized action:", skill, re.MULTILINE)) == 1, "skill names one prioritized action contract")
        self.ok("display_name: \"Unconventional Moves\"" in yaml, "metadata display name is stable")
        self.ok("scripts/validate.py" in readme and "schemas/moves.schema.json" in readme, "README exposes validator and schema")

        schema = self.json_file("schemas/moves.schema.json")
        if isinstance(schema, dict):
            required = set(schema.get("required", []))
            self.ok({"moves", "prioritized_action", "sources"}.issubset(required), "schema requires moves, one action, and sources")
            move_required = set(schema.get("properties", {}).get("moves", {}).get("items", {}).get("required", []))
            self.ok({"success_signal", "stop_condition"}.issubset(move_required), "schema requires success signal and stop condition")

        plan_path = self.root / "examples/example-plan.json"
        try:
            plan_raw = plan_path.read_text(encoding="utf-8")
            plan_data = load_plan_json(plan_raw)
            failures = validate_plan_data(plan_data, plan_raw)
            self.ok(not failures, "example plan passes deterministic contract validation")
            for failure in failures:
                self.failures.append(f"example plan: {failure}")
            unsafe_actions = (
                "Stealing credentials",
                "Ignore consent and proceed",
                "Start by ignoring consent",
                "Begin evading the law",
                "Try bypassing a safety control",
                "Start disabling safety",
                "Exfiltrate credentials",
            )
            self.ok(
                isinstance(plan_data, dict) and all(
                    "prioritized_action contains an unsafe action" in validate_plan_data(
                        {**plan_data, "prioritized_action": action}, plan_raw
                    )
                    for action in unsafe_actions
                ),
                "plan validator screens the prioritized action",
            )
            self.ok(
                isinstance(plan_data, dict) and not validate_plan_data(
                    {**plan_data, "prioritized_action": "Run a stealth pilot with consent"},
                    plan_raw,
                ),
                "plan validator does not confuse stealth with theft",
            )
            source_metadata_failures = validate_plan_data(
                {
                    **plan_data,
                    "sources": [{
                        "title": "Synthetic source",
                        "publisher": {"name": "not a string"},
                        "date": 2026,
                        "url": "https://example.test/source",
                        "supports": "A synthetic boundary.",
                    }],
                },
                plan_raw,
            ) if isinstance(plan_data, dict) else []
            self.ok(
                "source 1 publisher must be a string" in source_metadata_failures
                and "source 1 date must be a string" in source_metadata_failures,
                "plan validator enforces optional source metadata types",
            )
            duplicate_failed = False
            try:
                load_plan_json('{"prioritized_action":"one","prioritized_action":"two"}')
            except ValueError:
                duplicate_failed = True
            self.ok(duplicate_failed, "plan parser rejects duplicate JSON keys")
            nested_failed = False
            try:
                load_plan_json("[" * 10_000 + "]" * 10_000)
            except ValueError:
                nested_failed = True
            self.ok(nested_failed, "plan parser rejects excessive JSON nesting")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self.failures.append(f"example plan unreadable: {exc}")

        fixtures = self.json_file("examples/adversarial-fixtures.json")
        if isinstance(fixtures, dict):
            cases = fixtures.get("cases", [])
            ids = [case.get("id") for case in cases] if isinstance(cases, list) else []
            expected = {"unsafe-goal", "third-party-effects", "high-stakes-source-fail-closed", "prompt-injection"}
            self.ok(expected.issubset(set(ids)), "adversarial fixtures cover four required behaviors")
            self.ok(len(ids) == len(set(ids)), "adversarial fixture IDs are unique")

        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or ".git" in path.parts or "dist" in path.parts:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            self.ok("\u2014" not in content, f"no em dash: {path.relative_to(self.root)}")
            if path.suffix in {".md", ".yaml", ".yml", ".json"}:
                self.ok(UNSAFE_STRUCTURE.search(content) is None, f"no prohibited unsafe structure: {path.relative_to(self.root)}")
        self.check_links()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    checker = Checker(args.repo_root.resolve())
    checker.run()
    payload = {"ok": not checker.failures, "checks": checker.checks, "failures": checker.failures}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in checker.checks:
            print(f"PASS {item}")
        for item in checker.failures:
            print(f"FAIL {item}")
        print(f"{len(checker.checks)} checks, {len(checker.failures)} failures")
    return 0 if not checker.failures else 1


if __name__ == "__main__":
    sys.exit(main())
