#!/usr/bin/env python3
"""Build a deterministic installable ZIP and SHA-256 checksum."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

try:
    from .versioning import MAX_VERSION_LENGTH, VERSION_PATTERN, read_version
except ImportError:
    from versioning import MAX_VERSION_LENGTH, VERSION_PATTERN, read_version

__all__ = ["MAX_VERSION_LENGTH", "VERSION_PATTERN", "files_for", "main", "version_for"]

# The archive name comes from VERSION through the shared reader.
version_for = read_version


def files_for(root: Path) -> list[Path]:
    manifest_path = root / "package-manifest.json"
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries or any(not isinstance(item, str) for item in entries):
        raise ValueError("package-manifest.json must be a non-empty string array")
    if len(entries) != len(set(entries)):
        raise ValueError("package-manifest.json contains duplicate entries")
    result: list[Path] = []
    for entry in sorted(entries):
        relative = PurePosixPath(entry)
        if (relative.is_absolute() or entry != relative.as_posix()
                or "\\" in entry or ":" in entry or any(ord(char) < 32 for char in entry)
                or any(part in {"", ".", ".."} for part in relative.parts)):
            raise ValueError(f"unsafe package manifest entry: {entry}")
        path = root.joinpath(*relative.parts)
        if (not path.is_file() or any(parent.is_symlink() for parent in (path, *path.parents) if parent != root and root in parent.parents)
                or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError(f"missing or unsafe package file: {entry}")
        result.append(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    root = Path(__file__).resolve().parents[1]
    version = version_for(root)
    if args.output.is_symlink():
        raise FileExistsError('Choose a new output directory, not a symlink.')
    output_dir = args.output.resolve()
    if output_dir.exists():
        raise FileExistsError('Choose a new output directory.')
    archive = output_dir / f"unconventional-moves-{version}.zip"
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    files = files_for(root)
    prefix = f"unconventional-moves-{version}"
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # Publish the complete pair with one same-filesystem directory rename.
    # No existing output or partially promoted archive is replaced on failure.
    with TemporaryDirectory(dir=output_dir.parent, prefix='.unconventional-package-') as staging:
        staged_archive = Path(staging) / archive.name
        staged_checksum = Path(staging) / checksum.name
        with ZipFile(staged_archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as handle:
            for path in files:
                info = ZipInfo(f"{prefix}/{path.relative_to(root).as_posix()}")
                info.date_time = (2020, 1, 1, 0, 0, 0)
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                handle.writestr(info, path.read_bytes())
        digest = hashlib.sha256(staged_archive.read_bytes()).hexdigest()
        staged_checksum.write_bytes(f"{digest}  {archive.name}\n".encode("ascii"))
        if output_dir.exists() or output_dir.is_symlink():
            raise FileExistsError('Output appeared while packaging; choose a new directory.')
        Path(staging).rename(output_dir)
    print(archive)
    print(checksum)
    print(digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        print('FAIL package could not be created; verify sources and choose a new output directory', file=sys.stderr)
        raise SystemExit(1)
