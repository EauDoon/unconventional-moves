import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
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
