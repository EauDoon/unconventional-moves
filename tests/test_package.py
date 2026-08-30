import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.package import version_for


ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
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
            (root / "VERSION").write_text("../../../escape\n", encoding="utf-8")
            (root / "package-manifest.json").write_text("[]", encoding="utf-8")
            output = root / "dist"

            result = subprocess.run(
                [sys.executable, str(root / "scripts/package.py"), "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

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
