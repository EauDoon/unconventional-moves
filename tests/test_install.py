"""install_skill.py publishes a complete new copy or checks one, and never overwrites."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import install_skill

MANIFEST = json.loads((ROOT / "package-manifest.json").read_text(encoding="utf-8"))
SKILL_FILES = sorted(entry[len("skill/unconventional-moves/"):] for entry in MANIFEST
                     if entry.startswith("skill/unconventional-moves/"))


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts/install_skill.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def tree(path: Path) -> dict:
    return {item.relative_to(path).as_posix(): (item.read_bytes() if item.is_file() else None)
            for item in sorted(path.rglob("*"))}


class InstallTests(unittest.TestCase):
    def test_project_install_copies_exactly_the_manifest_skill_files(self):
        self.assertEqual(len(SKILL_FILES), 5)
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            result = run("--project", project)
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = project / ".agents/skills/unconventional-moves"
            files = sorted(item.relative_to(installed).as_posix() for item in installed.rglob("*") if item.is_file())
            self.assertEqual(files, SKILL_FILES)
            for relative in SKILL_FILES:
                self.assertEqual((installed / relative).read_bytes(),
                                 (ROOT / "skill/unconventional-moves" / relative).read_bytes())
            self.assertIn("SKILL.md", result.stdout)
            # No staging directory is left beside the install.
            self.assertEqual(sorted(item.name for item in installed.parent.iterdir()), ["unconventional-moves"])

    def test_dest_install_and_json_report(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "host-skill"
            result = run("--dest", destination, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["installed"], str(destination))
            self.assertEqual([item["path"] for item in report["files"]], SKILL_FILES)
            for item in report["files"]:
                self.assertEqual(item["sha256"], hashlib.sha256((destination / item["path"]).read_bytes()).hexdigest())

    def test_existing_destinations_are_refused_and_left_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            empty = root / "empty"
            empty.mkdir()
            occupied = root / "file"
            occupied.write_text("keep", encoding="utf-8")
            targets = [empty, occupied]
            link = root / "link"
            try:
                link.symlink_to(empty, target_is_directory=True)
                targets.append(link)
            except (OSError, NotImplementedError):
                pass  # Creating symlinks needs privilege on some Windows systems.
            for destination in targets:
                with self.subTest(destination=destination.name):
                    before = tree(root)
                    result = run("--dest", destination)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("destination already exists", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(tree(root), before)

    def test_a_file_in_place_of_the_skills_directory_is_named(self):
        for layout in (".agents", ".agents/skills"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as td:
                project = Path(td)
                blocker = project / layout
                blocker.parent.mkdir(parents=True, exist_ok=True)
                blocker.write_text("keep", encoding="utf-8")
                before = tree(project)
                result = run("--project", project)
                self.assertEqual(result.returncode, 1)
                self.assertIn("a file is in the way", result.stderr)
                self.assertNotIn("destination already exists", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(tree(project), before)

    def test_missing_project_or_parent_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            result = run("--project", Path(td) / "absent")
            self.assertEqual(result.returncode, 1)
            self.assertIn("project directory does not exist", result.stderr)
            result = run("--dest", Path(td) / "absent" / "skill")
            self.assertEqual(result.returncode, 1)
            self.assertIn("parent directory does not exist", result.stderr)
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_failed_publication_leaves_no_destination_or_staging(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "skill"
            def fail(path, target):
                raise PermissionError("injected publication failure")
            with patch.object(Path, "rename", fail), contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(install_skill.main(["--dest", str(destination)]), 1)
            self.assertIn("nothing was published", errors.getvalue())
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_destination_appearing_during_staging_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "skill"
            real = install_skill.sha256
            def appear(data):
                destination.mkdir(exist_ok=True)
                return real(data)
            with patch.object(install_skill, "sha256", appear), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(install_skill.main(["--dest", str(destination)]), 1)
            self.assertEqual(list(destination.iterdir()), [])
            self.assertEqual(sorted(item.name for item in Path(td).iterdir()), ["skill"])

    def test_target_options_are_exclusive_and_required(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(run().returncode, 2)
            self.assertEqual(run("--project", td, "--dest", Path(td) / "x").returncode, 2)
            self.assertEqual(list(Path(td).iterdir()), [])


class CheckTests(unittest.TestCase):
    def test_check_reports_identical_changed_missing_and_extra_without_writing(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            self.assertEqual(run("--project", project).returncode, 0)
            installed = project / ".agents/skills/unconventional-moves"
            result = run("--project", project, "--check")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("PASS installed skill matches the bundled files", result.stdout)
            with (installed / "SKILL.md").open("ab") as handle:
                handle.write(b"\nlocal edit\n")
            (installed / "references/strategy-review.md").unlink()
            (installed / "notes.txt").write_text("extra", encoding="utf-8")
            before = tree(project)
            result = run("--project", project, "--check", "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertFalse(report["identical"])
            statuses = {item["path"]: item["status"] for item in report["files"]}
            self.assertEqual(statuses, {"SKILL.md": "changed", "agents/openai.yaml": "identical",
                                        "notes.txt": "extra", "references/moves-v0.2.schema.json": "identical",
                                        "references/moves.schema.json": "identical",
                                        "references/strategy-review.md": "missing"})
            result = run("--dest", installed, "--check")
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL installed skill differs from the bundled files: 1 changed, 1 missing, 1 extra",
                          result.stdout)
            self.assertEqual(tree(project), before)

    def test_check_without_an_install_fails_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            result = run("--project", td, "--check")
            self.assertEqual(result.returncode, 1)
            self.assertIn("no installed skill directory", result.stderr)
            self.assertEqual(list(Path(td).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
