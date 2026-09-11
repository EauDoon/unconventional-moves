import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.package import (
    MAX_VERSION_LENGTH,
    files_for,
    version_for,
)

MAX_LENGTH_VERSION = f"1.{'9' * 60}.3"
OVERLONG_VERSION = f"1.{'9' * 61}.3"


class PackageTests(unittest.TestCase):
    def test_same_environment_builds_are_identical_and_complete(self):
        import hashlib
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            archives = []
            for name in ("first", "second"):
                output = Path(td) / name
                result = subprocess.run([sys.executable, str(ROOT / "scripts/package.py"), "--output", str(output)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                archive = next(output.glob("*.zip"))
                archives.append(archive.read_bytes())
                self.assertEqual(archive.with_suffix(".zip.sha256").read_text().split()[0],
                                 hashlib.sha256(archives[-1]).hexdigest())
                with zipfile.ZipFile(archive) as handle:
                    prefix = "unconventional-moves-" + version_for(ROOT) + "/"
                    self.assertEqual(sorted(handle.namelist()),
                                     sorted(prefix + path.relative_to(ROOT).as_posix() for path in files_for(ROOT)))
            self.assertEqual(*archives)

    def test_manifest_rejects_nonportable_names_and_symlink_ancestors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "folder").mkdir()
            (root / "folder" / "file.txt").write_text("synthetic", encoding="utf-8")
            manifest = root / "package-manifest.json"
            manifest.write_text(json.dumps(["folder/file.txt"]), encoding="utf-8")
            self.assertEqual(len(files_for(root)), 1)
            for entry in ("folder\\file.txt", "folder/../folder/file.txt", "C:folder/file.txt", "folder/file.txt\x00hidden"):
                manifest.write_text(json.dumps([entry]), encoding="utf-8")
                with self.subTest(entry=entry), self.assertRaises(ValueError):
                    files_for(root)
            # Simulate a symlink ancestor without requiring Windows symlink privilege.
            from unittest.mock import patch
            manifest.write_text(json.dumps(["folder/file.txt"]), encoding="utf-8")
            with patch.object(Path, "is_symlink", lambda path: path == root / "folder"):
                with self.assertRaises(ValueError):
                    files_for(root)

    def test_package_version_length_boundary(self):
        self.assertEqual(MAX_VERSION_LENGTH, 64)
        self.assertEqual(len(MAX_LENGTH_VERSION), 64)
        self.assertEqual(len(OVERLONG_VERSION), 65)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            version_path = root / "VERSION"
            version_path.write_text(MAX_LENGTH_VERSION, encoding="utf-8")
            self.assertEqual(version_for(root), MAX_LENGTH_VERSION)

            version_path.write_text(OVERLONG_VERSION, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at most 64 characters"):
                version_for(root)

    def test_package_version_cannot_escape_artifact_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            version_path = root / "VERSION"
            version_path.write_text("1.2.3\n", encoding="utf-8")
            self.assertEqual(version_for(root), "1.2.3")

            for invalid in (
                "",
                "1.2",
                "01.2.3",
                "1.2.3-alpha",
                "v1.2.3",
                " 1.2.3",
                "1.2.3 ",
                "1.2.3\n\n",
                "../../../escape",
                "1.2.3/../../escape",
                "1.2.3:*?",
                OVERLONG_VERSION,
            ):
                with self.subTest(version=invalid):
                    version_path.write_text(invalid, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "semantic X.Y.Z"):
                        version_for(root)

    def test_invalid_version_creates_no_output_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            (root / "scripts").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/package.py", root / "scripts/package.py")
            (root / "package-manifest.json").write_text("[]", encoding="utf-8")
            output = root / "dist"

            for invalid in (
                "../../../escape\n",
                f"{OVERLONG_VERSION}\n",
            ):
                with self.subTest(version=invalid.rstrip("\n")):
                    (root / "VERSION").write_text(invalid, encoding="utf-8")
                    before = {
                        path.relative_to(root).as_posix()
                        for path in root.rglob("*")
                    }

                    result = subprocess.run(
                        [sys.executable, str(root / "scripts/package.py"), "--output", str(output)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertEqual(
                        {
                            path.relative_to(root).as_posix()
                            for path in root.rglob("*")
                        },
                        before,
                    )

    def test_invalid_rebuild_preserves_previous_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            (root / "scripts").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/package.py", root / "scripts/package.py")
            (root / "VERSION").write_text("0.1.0\n", encoding="utf-8")
            (root / "payload.txt").write_text("release content\n", encoding="utf-8")
            manifest = root / "package-manifest.json"
            manifest.write_text(json.dumps(["payload.txt"]), encoding="utf-8")
            output = root / "dist"
            command = [sys.executable, str(root / "scripts/package.py"), "--output", str(output)]

            first = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            archive = output / "unconventional-moves-0.1.0.zip"
            checksum = archive.with_suffix(".zip.sha256")
            previous = archive.read_bytes(), checksum.read_bytes()

            manifest.write_text(json.dumps(["missing.txt"]), encoding="utf-8")
            failed = subprocess.run(command, capture_output=True, text=True, check=False)

            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((archive.read_bytes(), checksum.read_bytes()), previous)


if __name__ == "__main__":
    unittest.main()
