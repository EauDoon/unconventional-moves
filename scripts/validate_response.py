#!/usr/bin/env python3
"""Check that a prose skill response follows the documented output shape.

A completed response has five to seven `### Idea N: Title (mechanism)`
blocks numbered from 1, each with the seven labeled fields in order, an
optional Sources section after the ideas, and exactly one closing
`Prioritized action:` paragraph. This check is structural only. It never
scores quality, novelty, safety, or truth, and it never overrules the
behavioral evaluation gates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from .validate_plan import MAX_PLAN_BYTES, contains_unsafe_action, has_visible_text
    from .versioning import VersionAction
except ImportError:
    from validate_plan import MAX_PLAN_BYTES, contains_unsafe_action, has_visible_text
    from versioning import VersionAction

LABELS = ("Concrete move", "Why overlooked", "48-hour test", "Success signal",
          "Stop condition", "Evidence status", "Bounds")
# The plan validator screens these move fields plus the prioritized action.
SCREENED_LABELS = ("Concrete move", "48-hour test", "Success signal", "Stop condition")
NOT_COMPLETED = "not a completed plan (refusal, limitation, or non-trigger)"

_CANONICAL = {label.casefold(): label for label in LABELS}
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_IDEA = re.compile(r"^###[ \t]+Idea[ \t]+([0-9]+)[ \t]*:[ \t]*(.*?)[ \t]*$")
_MECHANISM = re.compile(r"^(.*?)[ \t]*\(([^()]*)\)$")
_BULLET = re.compile(r"^[-*+][ \t]+(.*)$")
_BOLD_LABEL = re.compile(r"^\*\*([^*:]+?)(?::\*\*|\*\*:)[ \t]*(.*)$")
_PLAIN_LABEL = re.compile(r"^([^*:]+?):(?:[ \t]+(.*))?$")
_PRIORITY = re.compile(r"^(?:\*\*Prioritized action(?::\*\*|\*\*:)|Prioritized action:)[ \t]*(.*)$")
_BOLD_SOURCES = re.compile(r"^\*\*Sources(?::\*\*|\*\*:?)[ \t]*$", re.IGNORECASE)


def _join(parts: list[str]) -> str:
    return " ".join(" ".join(part.split()) for part in parts if part.strip())


def _label(content: str) -> tuple[str, str] | None:
    match = _BOLD_LABEL.match(content) or _PLAIN_LABEL.match(content)
    if match is None:
        return None
    return " ".join(match.group(1).split()), match.group(2) or ""


def parse_response(text: str) -> dict:
    """Return the ideas, labeled fields, Sources markers, and priority paragraphs.

    Fenced code blocks are ignored. An indented non-blank line directly after
    a labeled bullet continues it, and the lines directly after a priority
    label continue that paragraph. Every field keeps its text with runs of
    whitespace joined into single spaces.
    """
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    ideas: list[dict] = []
    sources: list[int] = []
    priorities: list[dict] = []
    current: dict | None = None
    open_field: list[str] | None = None
    open_priority: list[str] | None = None
    fence: str | None = None
    content_lines: list[int] = []
    for number, line in enumerate(lines):
        if fence is not None:
            if line.lstrip(" ").startswith(fence):
                fence = None
            continue
        opening = _FENCE.match(line)
        if opening:
            fence = opening.group(1)[:3]
            open_field = open_priority = None
            content_lines.append(number)
            continue
        if not line.strip():
            open_field = open_priority = None
            continue
        content_lines.append(number)
        if open_priority is not None:
            # A heading, list item, or new marker interrupts the paragraph.
            if not (_HEADING.match(line) or _BULLET.match(line) or _BOLD_SOURCES.match(line)
                    or _PRIORITY.match(line)):
                open_priority.append(line)
                continue
            open_priority = None
        if open_field is not None and line[:1] in (" ", "\t") and not _HEADING.match(line):
            open_field.append(line)
            continue
        open_field = None
        idea = _IDEA.match(line)
        if idea:
            heading = idea.group(2)
            parts = _MECHANISM.match(heading)
            current = {"number": int(idea.group(1)), "line": number, "heading": heading,
                       "title": parts.group(1).strip() if parts else None,
                       "mechanism": parts.group(2).strip() if parts else None, "fields": []}
            ideas.append(current)
            continue
        heading = _HEADING.match(line)
        if heading:
            current = None
            if (heading.group(2) or "").rstrip(":").strip().casefold() == "sources":
                sources.append(number)
            continue
        if _BOLD_SOURCES.match(line):
            current = None
            sources.append(number)
            continue
        priority = _PRIORITY.match(line)
        if priority:
            current = None
            open_priority = [priority.group(1)]
            priorities.append({"line": number, "parts": open_priority})
            continue
        bullet = _BULLET.match(line)
        if bullet and current is not None:
            labeled = _label(bullet.group(1))
            if labeled is not None:
                open_field = [labeled[1]]
                current["fields"].append({"label": labeled[0], "parts": open_field})
    for idea in ideas:
        idea["fields"] = [{"label": field["label"], "text": _join(field["parts"])} for field in idea["fields"]]
    for priority in priorities:
        end = priority["line"] + len(priority["parts"]) - 1
        priority["text"] = _join(priority.pop("parts"))
        priority["end"] = end
    return {"ideas": ideas, "sources_lines": sources, "priorities": priorities,
            "last_content_line": content_lines[-1] if content_lines else None}


def idea_fields(idea: dict) -> dict[str, str]:
    """Map each documented label to its text; extra labels are left out."""
    result = {}
    for field in idea["fields"]:
        canonical = _CANONICAL.get(field["label"].casefold())
        if canonical is not None and canonical not in result:
            result[canonical] = field["text"]
    return result


def check_response(parsed: dict, high_stakes: bool = False) -> list[str]:
    """Return structural failures for a parsed response; empty means valid."""
    ideas, sources, priorities = parsed["ideas"], parsed["sources_lines"], parsed["priorities"]
    if not ideas and not priorities:
        return [NOT_COMPLETED]
    failures = []
    if not 5 <= len(ideas) <= 7:
        failures.append(f"a completed response needs five to seven ideas; found {len(ideas)}")
    numbers = [idea["number"] for idea in ideas]
    if numbers != list(range(1, len(ideas) + 1)):
        failures.append("ideas must be numbered 1 to N in order; found " + ", ".join(map(str, numbers)))
    for idea in ideas:
        label = f"idea {idea['number']}"
        if idea["mechanism"] is None or not has_visible_text(idea["mechanism"]):
            failures.append(f"{label} heading must end with a parenthesized mechanism")
        if idea["title"] is None or not has_visible_text(idea["title"]):
            failures.append(f"{label} heading must have a title before the mechanism")
        found = [_CANONICAL.get(field["label"].casefold()) for field in idea["fields"]]
        documented = [name for name in found if name is not None]
        for name in LABELS:
            count = documented.count(name)
            if count != 1:
                failures.append(f"{label} must have exactly one {name} field; found {count}")
        if all(documented.count(name) == 1 for name in LABELS) and documented != list(LABELS):
            failures.append(f"{label} fields must appear in the documented order: " + ", ".join(LABELS))
        texts = idea_fields(idea)
        for name in LABELS:
            if name in texts and not has_visible_text(texts[name]):
                failures.append(f"{label} {name} must have visible text")
        for name in SCREENED_LABELS:
            if name in texts and contains_unsafe_action(texts[name]):
                failures.append(f"{label} contains an unsafe action in {name}")
    if len(priorities) != 1:
        failures.append(f"a completed response ends with exactly one prioritized action; found {len(priorities)}")
    if priorities:
        priority = priorities[-1]
        if not has_visible_text(priority["text"]):
            failures.append("the prioritized action must have visible text")
        elif contains_unsafe_action(priority["text"]):
            failures.append("the prioritized action contains an unsafe action")
        if ideas and priority["line"] < ideas[-1]["line"]:
            failures.append("the prioritized action must come after the last idea")
        if any(line > priority["line"] for line in sources):
            failures.append("the Sources section must come before the prioritized action")
        if parsed["last_content_line"] is not None and parsed["last_content_line"] > priority["end"]:
            failures.append("nothing may follow the prioritized action paragraph")
    if ideas and any(line < ideas[-1]["line"] for line in sources):
        failures.append("the Sources section must come after the last idea")
    if high_stakes and not sources:
        failures.append("a high-stakes response needs a Sources section before the prioritized action")
    return failures


def validate_response_text(text: str, high_stakes: bool = False) -> tuple[list[str], dict]:
    parsed = parse_response(text)
    return check_response(parsed, high_stakes), parsed


def read_response_file(path: Path) -> str:
    """Read at most the plan byte bound as strict UTF-8, without a leading BOM."""
    with path.open("rb") as handle:
        raw = handle.read(MAX_PLAN_BYTES + 1)
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError(f"response exceeds {MAX_PLAN_BYTES} bytes")
    text = raw.decode("utf-8")
    return text[1:] if text.startswith("﻿") else text


def main(argv: list[str] | None = None) -> int:
    # Write UTF-8 with LF regardless of the console code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit 0 means the shape is valid, 1 means it is not or the file cannot be read, "
               "and 2 means invalid arguments. A valid shape is not a judgment of quality or safety.")
    parser.add_argument("--version", action=VersionAction)
    parser.add_argument("response", type=Path, help="a Markdown response saved as UTF-8 text")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a machine-readable report")
    parser.add_argument("--high-stakes", action="store_true",
                        help="also require a Sources section, as the skill does for high-stakes goals")
    args = parser.parse_args(argv)
    parsed = {"ideas": [], "sources_lines": [], "priorities": []}
    try:
        failures, parsed = validate_response_text(read_response_file(args.response), args.high_stakes)
    except OSError:
        failures = ["response file cannot be read"]
    except UnicodeDecodeError:
        failures = ["response must be UTF-8 text"]
    except ValueError as exc:
        failures = [str(exc)]
    completed = bool(parsed["ideas"] or parsed["priorities"])
    if args.as_json:
        print(json.dumps({"ok": not failures, "failures": failures, "ideas": len(parsed["ideas"]),
                          "sources_section": bool(parsed["sources_lines"]), "completed_plan": completed},
                         sort_keys=True))
        return int(bool(failures))
    if failures:
        for failure in failures:
            print("FAIL " + json.dumps(failure, ensure_ascii=True)[1:-1])
        return 1
    print(f"PASS valid response: {args.response}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
