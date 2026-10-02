import json
import os
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.package import (
    MAX_VERSION_LENGTH,
    files_for,
    version_for,
    main as package_main,
)

MAX_LENGTH_VERSION = f"1.{'9' * 60}.3"
OVERLONG_VERSION = f"1.{'9' * 61}.3"


class PackageTests(unittest.TestCase):
    def test_unicode_output_path_reports_success_with_ascii_process_encoding(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'caf\u00e9-\u6771\u4eac'
            result = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/package.py'), '--output', str(output)],
                env={**os.environ, 'PYTHONIOENCODING': 'ascii'}, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = next(output.glob('*.zip'))
            self.assertIn(str(archive.resolve()), result.stdout.decode('utf-8'))
            self.assertEqual(archive.with_suffix('.zip.sha256').read_text(encoding='ascii').split()[0],
                             hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_fresh_output_contract_and_pair_publication_failure(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td).resolve()
            output = parent / 'release'
            with patch('sys.argv', ['package.py', '--output', str(output)]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(package_main(), 0)
                before = {path.name: path.read_bytes() for path in output.iterdir()}
                with self.assertRaises(FileExistsError):
                    package_main()
                self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, before)
            empty = parent / 'empty'; empty.mkdir()
            with patch('sys.argv', ['package.py', '--output', str(empty)]), self.assertRaises(FileExistsError):
                package_main()
            self.assertEqual(list(empty.iterdir()), [])
            for failure in ['checksum', 'publish']:
                fresh = parent / failure
                write_bytes, rename = Path.write_bytes, Path.rename
                def fail_checksum(path, data):
                    if path.suffix == '.sha256':
                        raise PermissionError('injected checksum failure')
                    return write_bytes(path, data)
                def fail_publish(path, target):
                    raise PermissionError('injected publication failure')
                with patch('sys.argv', ['package.py', '--output', str(fresh)]), \
                     patch.object(Path, 'write_bytes', fail_checksum if failure == 'checksum' else write_bytes), \
                     patch.object(Path, 'rename', fail_publish if failure == 'publish' else rename), \
                     self.assertRaises(PermissionError):
                    package_main()
                self.assertFalse(fresh.exists())
                self.assertEqual(sorted(path.name for path in parent.iterdir()), ['empty', 'release'])
                self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, before)

    def test_package_includes_the_eval_runner(self):
        entries = json.loads((ROOT / "package-manifest.json").read_text(encoding="utf-8"))
        self.assertIn("evals/runner.py", entries)
        self.assertIn("evals/cases/unsafe-objective.json", entries)
        packaged = files_for(ROOT)
        self.assertIn(ROOT / "evals" / "runner.py", packaged)
        self.assertEqual(sum(1 for path in packaged if path.parent.name == "cases"), 20)

    def test_extracted_package_replays_verified_handoff_recovery(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = subprocess.run([sys.executable, str(ROOT / "scripts/package.py"),
                                     "--output", str(root / "dist")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(next((root / "dist").glob("*.zip"))) as archive:
                archive.extractall(root / "extracted")
            package = root / "extracted" / ("unconventional-moves-" + version_for(ROOT))
            # Run away from both the checkout and package; use only shipped files.
            replay = root / "replay"
            result = subprocess.run([sys.executable, str(package / "examples/replay-handoff.py"),
                                     "--output", str(replay)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((replay / "replay-summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["synthetic_only"])
            self.assertEqual(summary["decision"], "stop_and_review")
            self.assertEqual(summary["restored_checkpoints"], 3)
            self.assertTrue(summary["old_history_rejected_for_revision"])
            for args in (["scripts/validate.py"],
                         ["evals/runner.py"],
                         ["scripts/moves_cli.py", "unpack-handoff", str(replay / "handoff.json"),
                          "--output-dir", str(root / "shim-restored")],
                         ["scripts/moves.py", "render", "examples/example-plan.json"]):
                result = subprocess.run([sys.executable, *args], cwd=package, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Neither replay nor recovery may overwrite an earlier result.
            original = (replay / "replay-summary.json").read_bytes()
            result = subprocess.run([sys.executable, str(package / "examples/replay-handoff.py"),
                                     "--output", str(replay)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual((replay / "replay-summary.json").read_bytes(), original)

    def test_extracted_unicode_adoption_with_ascii_process_encoding(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/package.py'), '--output', str(root / 'dist')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(next((root / 'dist').glob('*.zip'))) as archive:
                archive.extractall(root / 'extracted')
            package = root / 'extracted' / ('unconventional-moves-' + version_for(ROOT))
            env = {**os.environ, 'PYTHONIOENCODING': 'ascii', 'PYTHONDONTWRITEBYTECODE': '1'}
            def run(*args):
                result = subprocess.run([sys.executable, str(package / 'scripts/moves.py'), *map(str, args)],
                                        cwd=root, env=env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
                return result.stdout.decode('utf-8')
            def read(path):
                return json.loads(path.read_text(encoding='utf-8'))
            def write(path, value):
                path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            plan = read(package / 'examples/bounded-plan.json')
            plan['goal'] = 'Practice caf\u00e9 vocabulary for \u6771\u4eac'
            plan_path = root / 'plan.json'; write(plan_path, plan)
            original = plan_path.read_bytes()
            validation = subprocess.run([sys.executable, str(package / 'scripts/validate_plan.py'), str(plan_path), '--json'],
                                        cwd=root, env=env, capture_output=True)
            self.assertEqual(validation.returncode, 0, validation.stderr)
            before = set(root.rglob('*'))
            rendered = run('render', plan_path)
            self.assertIn(plan['goal'], rendered)
            self.assertEqual(set(root.rglob('*')), before, 'read-only rendering writes no files')
            run('render', plan_path, '--output', root / 'render.md')
            self.assertEqual((root / 'render.md').read_text(encoding='utf-8'), rendered)
            run('observation-draft', plan_path, '--output', root / 'draft.json')
            observation = read(root / 'draft.json')
            observation.update(elapsed_hours=1, active_minutes=1, stop_triggered=True,
                               notes='Fictional caf\u00e9 checkpoint in \u6771\u4eac. Stop remains binding.')
            write(root / 'history.json', [observation])
            run('handoff', plan_path, '--timeline', root / 'history.json', '--output', root / 'handoff.json')
            bundle = read(root / 'handoff.json')
            self.assertTrue(json.loads(run('verify-handoff', root / 'handoff.json'))['consistent'])
            run('unpack-handoff', root / 'handoff.json', '--output-dir', root / 'restored')
            self.assertEqual(read(root / 'restored/plan.json'), plan)
            self.assertEqual(read(root / 'restored/checkpoints.json'), [observation])
            restored = read(root / 'restored/handoff.json')
            self.assertEqual(restored['plan_sha256'], bundle['plan_sha256'])
            resumed = json.loads(run('timeline', root / 'restored/plan.json', root / 'restored/checkpoints.json'))
            self.assertEqual(resumed['decision'], 'stop_and_review')
            self.assertEqual(plan_path.read_bytes(), original)

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
