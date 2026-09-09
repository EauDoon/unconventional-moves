#!/usr/bin/env python3
"""Dependency-light repository checks for Unconventional Moves."""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import chain
from pathlib import Path
from urllib.parse import unquote, urlsplit

from validate_plan import load_plan_json, validate_plan_data

UNSAFE_STRUCTURE = re.compile(r"(?i)\b(?:ignore\s+(?:consent|scope|safety)|disable\s+safety|exfiltrat\w*)\b")
EXTERNAL_SCHEMES = {"http", "https", "mailto"}
MARKDOWN_ESCAPABLE = frozenset(r'!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')
# Em dash (U+2014, ASCII minus here), en dash (U+2013, ASCII minus here), figure dash (U+2012), horizontal bar (U+2015),
# minus sign (U+2212), and the mdash entity / ndash entity HTML entities.
_DASH_CHARS = frozenset("\u2012\u2013\u2014\u2015\u2212")
_DASH_ENTITIES = (chr(0x26) + "mdash" + chr(0x3B), chr(0x26) + "ndash" + chr(0x3B))


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _unescape_markdown(value: str) -> str:
    result: list[str] = []
    cursor = 0
    while cursor < len(value):
        if (
            value[cursor] == "\\"
            and cursor + 1 < len(value)
            and value[cursor + 1] in MARKDOWN_ESCAPABLE
        ):
            result.append(value[cursor + 1])
            cursor += 2
        else:
            result.append(value[cursor])
            cursor += 1
    return "".join(result)


def _parse_link_title(text: str, cursor: int) -> int:
    opener = text[cursor]
    closer = ")" if opener == "(" else opener
    cursor += 1
    while cursor < len(text):
        if text[cursor] in "\r\n":
            raise ValueError("link title contains a line break")
        if text[cursor] == "\\" and cursor + 1 < len(text):
            cursor += 2
            continue
        if text[cursor] == closer:
            return cursor + 1
        cursor += 1
    raise ValueError("link title is not terminated")


def inline_link_targets(text: str):
    """Yield every inline Markdown destination and fail closed on malformed syntax."""
    search_from = 0
    while True:
        marker = text.find("](", search_from)
        if marker < 0:
            return
        search_from = marker + 2
        if _is_escaped(text, marker):
            continue

        cursor = marker + 2
        while cursor < len(text) and text[cursor] in " \t":
            cursor += 1
        destination_start = cursor

        try:
            if cursor >= len(text):
                raise ValueError("link destination is missing")

            if text[cursor] == "<":
                cursor += 1
                destination_start = cursor
                while cursor < len(text):
                    if text[cursor] in "\r\n":
                        raise ValueError("angle-bracket destination contains a line break")
                    if text[cursor] == "\\" and cursor + 1 < len(text):
                        cursor += 2
                        continue
                    if text[cursor] == ">":
                        break
                    cursor += 1
                if cursor >= len(text) or text[cursor] != ">":
                    raise ValueError("angle-bracket destination is not terminated")
                raw_target = text[destination_start:cursor]
                cursor += 1
            else:
                depth = 0
                while cursor < len(text):
                    character = text[cursor]
                    if character == "\\" and cursor + 1 < len(text):
                        cursor += 2
                        continue
                    if character == "(":
                        depth += 1
                        if depth > 32:
                            raise ValueError("link destination nesting exceeds 32 levels")
                    elif character == ")":
                        if depth == 0:
                            break
                        depth -= 1
                    elif character in " \t\r\n":
                        if depth:
                            raise ValueError("link destination has unbalanced parentheses")
                        break
                    cursor += 1
                if depth:
                    raise ValueError("link destination has unbalanced parentheses")
                raw_target = text[destination_start:cursor]

            while cursor < len(text) and text[cursor] in " \t":
                cursor += 1
            if cursor < len(text) and text[cursor] in {'"', "'", "("}:
                cursor = _parse_link_title(text, cursor)
                while cursor < len(text) and text[cursor] in " \t":
                    cursor += 1
            if cursor >= len(text) or text[cursor] != ")":
                raise ValueError("inline link is not terminated")

            yield _unescape_markdown(raw_target), None
            search_from = cursor + 1
        except ValueError as exc:
            yield None, f"offset {marker}: {exc}"


def reference_definition_bodies(text: str):
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        indent = len(line) - len(line.lstrip(" "))
        if indent <= 3 and indent < len(line) and line[indent] == "[":
            cursor = indent + 1
            label_has_content = False
            while cursor < len(line):
                if line[cursor] == "\\" and cursor + 1 < len(line):
                    label_has_content = True
                    cursor += 2
                    continue
                if line[cursor] == "]":
                    if label_has_content and cursor + 1 < len(line) and line[cursor + 1] == ":":
                        yield line[cursor + 2:].lstrip(" \t"), offset + indent
                    break
                label_has_content = True
                cursor += 1
        offset += len(raw_line)


def reference_link_targets(text: str):
    """Yield destinations from CommonMark reference definitions."""
    for body, offset in reference_definition_bodies(text):
        if not body:
            yield None, f"offset {offset}: multiline reference definition is unsupported"
            continue
        parsed = list(inline_link_targets(f"[reference]({body})"))
        if len(parsed) != 1:
            yield None, f"offset {offset}: reference definition is ambiguous"
            continue
        target, syntax_error = parsed[0]
        if syntax_error:
            yield None, f"offset {offset}: invalid reference definition ({syntax_error})"
        else:
            yield target, None


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
        root_resolved = self.root.resolve()
        for path in sorted(self.root.rglob("*.md")):
            if ".git" in path.parts or "dist" in path.parts:
                continue
            content = path.read_text(encoding="utf-8")
            targets = chain(inline_link_targets(content), reference_link_targets(content))
            for target, syntax_error in targets:
                if syntax_error:
                    self.ok(
                        False,
                        f"link syntax is valid: {path.relative_to(self.root)} -> {syntax_error}",
                    )
                    continue
                assert target is not None
                try:
                    parsed = urlsplit(target)
                except ValueError:
                    self.ok(
                        False,
                        f"link target is valid: {path.relative_to(self.root)} -> {target}",
                    )
                    continue
                if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
                    continue
                if not parsed.path:
                    continue
                try:
                    relative = unquote(parsed.path, encoding="utf-8", errors="strict")
                except UnicodeDecodeError:
                    self.ok(
                        False,
                        f"link path is UTF-8: {path.relative_to(self.root)} -> {target}",
                    )
                    continue
                portable_relative = relative.replace("\\", "/")
                candidate = (path.parent / portable_relative).resolve()
                inside_repo = candidate == root_resolved or root_resolved in candidate.parents
                self.ok(
                    inside_repo,
                    f"link stays inside repo: {path.relative_to(self.root)} -> {target}",
                )
                if not inside_repo:
                    continue
                self.ok(candidate.exists(), f"link exists: {path.relative_to(self.root)} -> {target}")

    def run(self) -> None:
        skill = self.read("skill/unconventional-moves/SKILL.md")
        readme = self.read("README.md")
        yaml = self.read("skill/unconventional-moves/agents/openai.yaml")
        self.ok(skill.startswith(("\n---", "---")), "SKILL.md has frontmatter")
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

        for name in ("moves.schema.json", "moves-v0.2.schema.json"):
            canonical = self.root / "schemas" / name
            bundled = self.root / "skill/unconventional-moves/references" / name
            self.ok(canonical.is_file() and bundled.is_file() and canonical.read_bytes() == bundled.read_bytes(),
                    f"installed schema matches canonical: {name}")

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
            self.ok(_DASH_CHARS.isdisjoint(content) and not any(entity in content for entity in _DASH_ENTITIES), f"no em or en dash: {path.relative_to(self.root)}")
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
