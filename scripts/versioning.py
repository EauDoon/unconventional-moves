#!/usr/bin/env python3
"""Read the package version and check it against CHANGELOG.md.

VERSION at the repository root is the single source of truth. CHANGELOG.md
follows Keep a Changelog: an [Unreleased] section first, then dated releases
from newest to oldest. The newest release must equal VERSION.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
# Keep the version-derived archive name comfortably below common 255-byte
# filename-component limits. The accepted grammar is ASCII-only.
MAX_VERSION_LENGTH = 64

UNRELEASED_HEADING = "## [Unreleased]"
# ASCII digits only: str patterns would otherwise accept other Unicode digits.
RELEASE_HEADING = re.compile(
    r"## \[((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\] - ([0-9]{4}-[0-9]{2}-[0-9]{2})"
)
LINK_REFERENCE = re.compile(r"\[[^\]]+\]: \S")


def read_version(root: Path = ROOT) -> str:
    raw = (root / "VERSION").read_text(encoding="utf-8")
    version = raw.removesuffix("\n")
    if len(version) > MAX_VERSION_LENGTH or VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(
            f"VERSION must contain a semantic X.Y.Z version of at most {MAX_VERSION_LENGTH} characters"
        )
    return version


class VersionAction(argparse.Action):
    """A --version option that reads VERSION only when it is used."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS,
                 help="print the package version and exit"):
        super().__init__(option_strings=option_strings, dest=dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        try:
            version = read_version(ROOT)
        except (OSError, ValueError):
            print("FAIL VERSION is missing or invalid", file=sys.stderr)
            parser.exit(1)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
        print(f"unconventional-moves {version}")
        parser.exit(0)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Split Markdown into (level-two heading, body lines) pairs."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line.rstrip(), []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def _read_changelog(root: Path) -> str | None:
    try:
        return (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def changelog_problems(root: Path = ROOT, version: str | None = None) -> list[str]:
    """Return every way CHANGELOG.md disagrees with the release contract."""
    if version is None:
        try:
            version = read_version(root)
        except (OSError, UnicodeDecodeError, ValueError):
            return ["VERSION is missing or invalid"]
    text = _read_changelog(root)
    if text is None:
        return ["CHANGELOG.md is missing or not UTF-8"]
    sections = _sections(text)
    if not sections or sections[0][0] != UNRELEASED_HEADING:
        return [f"the first section must be {UNRELEASED_HEADING}"]
    problems: list[str] = []
    releases: list[tuple[str, date]] = []
    for heading, _body in sections[1:]:
        if heading == UNRELEASED_HEADING:
            problems.append(f"{UNRELEASED_HEADING} appears more than once")
            continue
        match = RELEASE_HEADING.fullmatch(heading)
        if match is None:
            problems.append(f"heading is not a dated release '## [X.Y.Z] - YYYY-MM-DD': {heading}")
            continue
        try:
            released = date.fromisoformat(match.group(2))
        except ValueError:
            problems.append(f"release date is not a real date: {heading}")
            continue
        releases.append((match.group(1), released))
    for (newer, newer_date), (older, older_date) in zip(releases, releases[1:]):
        if _version_key(newer) <= _version_key(older):
            problems.append(f"releases must be listed newest first without repeats: {newer} before {older}")
        if newer_date < older_date:
            problems.append(f"release dates must not increase down the file: {newer} {newer_date} before {older} {older_date}")
    if not releases:
        problems.append(f"no dated release matches VERSION {version}")
    elif releases[0][0] != version:
        problems.append(f"newest release {releases[0][0]} does not match VERSION {version}")
    return problems


def release_notes(root: Path, version: str) -> str | None:
    """Return the body of the dated section for version, without its heading."""
    text = _read_changelog(root)
    if text is None:
        return None
    for heading, body in _sections(text):
        match = RELEASE_HEADING.fullmatch(heading)
        if match is None or match.group(1) != version:
            continue
        lines = [line for line in body if not LINK_REFERENCE.match(line)]
        return "\n".join(lines).strip("\n") + "\n"
    return None
