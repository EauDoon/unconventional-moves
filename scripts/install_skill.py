#!/usr/bin/env python3
"""Install the bundled skill into a new directory, or check an installed copy.

The files installed are the skill entries of package-manifest.json, so caches
and stray files never ship. Installation refuses any existing destination,
stages a complete copy beside it, checks every staged file against its source,
and publishes it with one directory rename. --check compares an installed copy
with the bundled files and writes nothing. The tool never overwrites, merges,
or deletes an installed skill, and reads no environment variable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

try:
    from .package import files_for
    from .versioning import VersionAction
except ImportError:
    from package import files_for
    from versioning import VersionAction

SKILL_PREFIX = "skill/unconventional-moves/"
SKILL_NAME = "unconventional-moves"


class InstallError(Exception):
    """A refusal with a message for the user."""


def bundled_files(root: Path) -> dict[str, Path]:
    """Map each installed relative path to its source, from the package manifest."""
    files = {}
    for path in files_for(root):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(SKILL_PREFIX):
            files[relative[len(SKILL_PREFIX):]] = path
    if "SKILL.md" not in files:
        raise InstallError("package-manifest.json lists no skill/unconventional-moves/SKILL.md")
    return dict(sorted(files.items()))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def install(root: Path, destination: Path) -> list[dict]:
    sources = {relative: path.read_bytes() for relative, path in bundled_files(root).items()}
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    parent = destination.parent
    if not parent.is_dir():
        raise InstallError("the destination's parent directory does not exist")
    # Stage beside the destination so the final rename stays on one filesystem.
    with TemporaryDirectory(dir=parent, prefix=".unconventional-skill-") as staging:
        stage = Path(staging) / SKILL_NAME
        for relative, data in sources.items():
            target = stage.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(data)
        for relative, data in sources.items():
            if sha256(stage.joinpath(*PurePosixPath(relative).parts).read_bytes()) != sha256(data):
                raise InstallError("a staged file does not match its source: " + relative)
        # On POSIX a rename onto an existing empty directory replaces it, so
        # check again immediately before publishing.
        if os.path.lexists(destination):
            raise FileExistsError(destination)
        stage.rename(destination)
    return [{"path": relative, "sha256": sha256(data)} for relative, data in sources.items()]


def check(root: Path, destination: Path) -> list[dict]:
    """Compare an installed copy with the bundled files without writing anything."""
    if os.path.islink(destination) or not destination.is_dir():
        raise InstallError("no installed skill directory at the destination")
    expected = {relative: sha256(path.read_bytes()) for relative, path in bundled_files(root).items()}
    found: dict[str, str | None] = {}
    for current, directories, names in os.walk(destination, followlinks=False):
        base = Path(current)
        for name in [*directories, *names]:
            path = base / name
            relative = path.relative_to(destination).as_posix()
            if path.is_symlink():
                found[relative] = None  # Reported, never followed.
            elif path.is_file():
                found[relative] = sha256(path.read_bytes())
    report = []
    for relative in sorted(expected.keys() | found.keys()):
        if relative not in found:
            status = "missing"
        elif relative not in expected:
            status = "extra"
        else:
            status = "identical" if found[relative] == expected[relative] else "changed"
        report.append({"path": relative, "status": status})
    return report


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="To upgrade an install: run --check, keep a backup, move the old directory away yourself, "
               "then install. Exit 0 means installed or identical, 1 a refusal or a difference, 2 bad arguments.")
    parser.add_argument("--version", action=VersionAction)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", type=Path, metavar="DIR",
                        help="an existing project directory; installs to DIR/.agents/skills/unconventional-moves")
    target.add_argument("--dest", type=Path, metavar="DIR",
                        help="an explicit new skill directory for another host; its parent must exist")
    parser.add_argument("--check", action="store_true",
                        help="compare an installed copy with the bundled files instead of installing")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a machine-readable report")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if args.project is not None:
            if not args.project.is_dir():
                raise InstallError("the project directory does not exist")
            destination = args.project / ".agents" / "skills" / SKILL_NAME
            if not args.check:
                destination.parent.mkdir(parents=True, exist_ok=True)
        else:
            destination = args.dest
        if args.check:
            report = check(root, destination)
            identical = all(item["status"] == "identical" for item in report)
            if args.as_json:
                print(json.dumps({"destination": str(destination), "identical": identical, "files": report},
                                 sort_keys=True))
            else:
                for item in report:
                    print(f"{item['status']} {item['path']}")
                counts = {status: sum(item["status"] == status for item in report)
                          for status in ("changed", "missing", "extra")}
                if identical:
                    print(f"PASS installed skill matches the bundled files: {destination}")
                else:
                    print("FAIL installed skill differs from the bundled files: "
                          + ", ".join(f"{count} {status}" for status, count in counts.items()))
            return 0 if identical else 1
        installed = install(root, destination)
    except FileExistsError:
        print("FAIL destination already exists; choose a new destination, or run --check and move the old "
              "install away yourself", file=sys.stderr)
        return 1
    except InstallError as exc:
        print("FAIL " + str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("FAIL skill could not be installed; nothing was published at the destination", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps({"installed": str(destination), "files": installed}, sort_keys=True))
    else:
        print(f"installed {destination}")
        for item in installed:
            print(f"{item['sha256']}  {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
