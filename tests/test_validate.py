import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate import Checker, UNSAFE_STRUCTURE
from validate_plan import contains_unsafe_action
from validate_plan import load_plan_json, validate_plan_data
from validate_plan import main as validate_plan_main
from versioning import changelog_problems, release_notes


VALID_CHANGELOG = (
    "# Changelog\n\n"
    "## [Unreleased]\n\n### Fixed\n\n- Synthetic pending fix.\n\n"
    "## [0.2.0] - 2026-09-09\n\n### Added\n\n- Synthetic second release.\n\n"
    "## [0.1.0] - 2026-08-03\n\n### Added\n\n- Synthetic first release.\n\n"
    "[Unreleased]: https://example.test/compare/v0.2.0...HEAD\n"
    "[0.2.0]: https://example.test/compare/v0.1.0...v0.2.0\n"
    "[0.1.0]: https://example.test/releases/tag/v0.1.0\n"
)


class ChangelogTests(unittest.TestCase):
    def problems_for(self, changelog: str, version: str = "0.2.0") -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text(version + "\n", encoding="utf-8")
            (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
            return changelog_problems(root)

    def test_repository_changelog_matches_version(self) -> None:
        self.assertEqual(changelog_problems(ROOT), [])

    def test_valid_synthetic_changelog_passes(self) -> None:
        self.assertEqual(self.problems_for(VALID_CHANGELOG), [])

    def test_each_contract_violation_is_reported(self) -> None:
        cases = {
            "newest release ahead of VERSION": VALID_CHANGELOG.replace(
                "## [0.2.0] - 2026-09-09", "## [0.3.0] - 2026-09-11\n\n- Premature.\n\n## [0.2.0] - 2026-09-09"),
            "missing unreleased": VALID_CHANGELOG.replace("## [Unreleased]\n\n### Fixed\n\n- Synthetic pending fix.\n\n", ""),
            "undated release": VALID_CHANGELOG.replace("## [0.2.0] - 2026-09-09", "## 0.2.0"),
            "impossible date": VALID_CHANGELOG.replace("2026-09-09", "2026-02-30"),
            "ascending versions": VALID_CHANGELOG.replace("[0.1.0] - 2026-08-03", "[0.3.0] - 2026-08-03"),
            "dates increase downward": VALID_CHANGELOG.replace("2026-08-03", "2026-10-01"),
            "duplicate unreleased": VALID_CHANGELOG.replace("## [0.1.0]", "## [Unreleased]\n\n## [0.1.0]"),
            "non-ASCII digits": VALID_CHANGELOG.replace("[0.2.0] - 2026-09-09", "[0.2.0] - 2026-09-0\uff19"),
        }
        for name, changelog in cases.items():
            with self.subTest(case=name):
                self.assertTrue(self.problems_for(changelog), name)

    def test_version_without_matching_release_fails_repository_check(self) -> None:
        self.assertTrue(any("does not match VERSION 0.9.9" in problem
                            for problem in self.problems_for(VALID_CHANGELOG, "0.9.9")))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("0.9.9\n", encoding="utf-8")
            (root / "CHANGELOG.md").write_text(VALID_CHANGELOG, encoding="utf-8")
            checker = Checker(root)
            checker.run()
            self.assertIn("VERSION matches the newest CHANGELOG release", checker.failures)
            self.assertTrue(any(item.startswith("changelog: newest release") for item in checker.failures))

    def test_missing_files_are_problems_not_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(changelog_problems(root), ["VERSION is missing or invalid"])
            (root / "VERSION").write_text("0.2.0\n", encoding="utf-8")
            self.assertEqual(changelog_problems(root), ["CHANGELOG.md is missing or not UTF-8"])
            (root / "CHANGELOG.md").write_bytes(b"## [Unreleased]\n\xff\n")
            self.assertEqual(changelog_problems(root), ["CHANGELOG.md is missing or not UTF-8"])

    def test_release_notes_return_one_section_without_link_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CHANGELOG.md").write_text(VALID_CHANGELOG, encoding="utf-8")
            self.assertEqual(release_notes(root, "0.2.0"), "### Added\n\n- Synthetic second release.\n")
            self.assertEqual(release_notes(root, "0.1.0"), "### Added\n\n- Synthetic first release.\n")
            self.assertIsNone(release_notes(root, "9.9.9"))


class Utf8OutputTests(unittest.TestCase):
    """Printed paths must not depend on the console encoding."""

    ASCII_ENV = {**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONDONTWRITEBYTECODE": "1"}

    def test_validate_plan_reports_a_unicode_path_with_ascii_process_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "caf\u00e9-\u6771\u4eac"
            folder.mkdir()
            plan = folder / "plan.json"
            shutil.copy2(ROOT / "examples/example-plan.json", plan)
            for extra in ((), ("--json",)):
                with self.subTest(extra=extra):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "scripts/validate_plan.py"), str(plan), *extra],
                        env=self.ASCII_ENV, capture_output=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
                    self.assertNotIn(b"Traceback", result.stderr)
                    stdout = result.stdout.decode("utf-8")
                    if extra:
                        self.assertEqual(json.loads(stdout), {"ok": True, "failures": []})
                    else:
                        self.assertIn(str(plan), stdout)

    def test_repository_check_reports_a_unicode_file_name_with_ascii_process_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "caf\u00e9.md").write_text("# Synthetic note\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/validate.py"), "--repo-root", str(root)],
                env=self.ASCII_ENV, capture_output=True,
            )
            # Required repository files are missing, so the check fails cleanly.
            self.assertEqual(result.returncode, 1, result.stderr.decode("utf-8", "replace"))
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertIn("caf\u00e9.md", result.stdout.decode("utf-8"))


class WorkflowPinTests(unittest.TestCase):
    def test_workflow_actions_are_pinned_to_full_commit_shas(self):
        workflows = ROOT / ".github" / "workflows"
        if not workflows.is_dir():
            self.skipTest("workflows are not shipped in the package")
        # A full commit SHA cannot be moved like a tag; the version comment
        # lets Dependabot and reviewers read which release it is.
        pinned = re.compile(r"\s*(?:-\s+)?uses:\s+[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40} # v[0-9]+\.[0-9]+\.[0-9]+\s*")
        uses = []
        for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.match(r"\s*(?:-\s+)?uses:", line):
                    uses.append((path.name, number, line))
        self.assertTrue(uses, "no workflow step uses an action")
        for name, number, line in uses:
            with self.subTest(workflow=name, line=number):
                self.assertIsNotNone(pinned.fullmatch(line), line)

    def test_workflow_expressions_stay_out_of_run_scripts(self):
        workflows = ROOT / ".github" / "workflows"
        if not workflows.is_dir():
            self.skipTest("workflows are not shipped in the package")
        # An expression expanded inside a run script is spliced into shell
        # source before it runs. Pass values through env or with: instead.
        allowed = re.compile(r"\s*(?:group|cancel-in-progress|runs-on|python-version|subject-path|GH_TOKEN|GH_REPO):\s")
        for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "${{" in line:
                    with self.subTest(workflow=path.name, line=number):
                        self.assertIsNotNone(allowed.match(line), line)

    def test_release_workflow_runs_only_for_version_tags(self):
        release = ROOT / ".github" / "workflows" / "release.yml"
        if not release.is_file():
            self.skipTest("workflows are not shipped in the package")
        text = release.read_text(encoding="utf-8")
        self.assertIn('tags: ["v*.*.*"]', text)
        self.assertNotIn("pull_request", text)
        self.assertIn("python scripts/versioning.py --check-tag", text)
        self.assertLess(text.index("--check-tag"), text.index("gh release create"))
        for permission in ("contents: write", "id-token: write", "attestations: write"):
            self.assertIn(permission, text)


class ValidateTests(unittest.TestCase):
    def test_repository_screen_distinguishes_boundary_from_action(self):
        self.assertFalse(contains_unsafe_action("Never ignore consent.", UNSAFE_STRUCTURE))
        self.assertFalse(contains_unsafe_action('Review the warning: "Do not disable safety controls."', UNSAFE_STRUCTURE))
        self.assertTrue(contains_unsafe_action("Never hesitate to ignore consent.", UNSAFE_STRUCTURE))
        self.assertTrue(contains_unsafe_action("Never ignore consent. Then disable safety controls.", UNSAFE_STRUCTURE))

    def test_prevention_mentions_do_not_hide_prohibited_actions(self):
        plan = json.loads((ROOT / "examples/example-plan.json").read_text(encoding="utf-8"))
        benign = (
            "Do not steal credentials.",
            "Never ignore consent.",
            "Prevent harassment.",
            "Stop if harassment occurs.",
            'Review the warning: "Do not disable safety controls."',
        )
        prohibited = (
            "Steal credentials.", "Start disabling safety controls.",
            "Do not hesitate to steal credentials.",
            "Do not stop stealing credentials.",
            "Do not steal credentials unless access is refused.",
            "Do not steal credentials, unless access is refused.",
            "Never ignore consent except during the pilot.",
            "Never ignore consent, except during the pilot.",
            "Do not disable safety controls without approval.",
            "Never ask permission; ignore consent.",
            "Do not steal credentials, but ignore consent.",
            "Prevent harassment and steal credentials.",
            'Review the warning: "Do not steal credentials." Then disable safety controls.',
        )
        for field in ("concrete_move", "test_48h", "success_signal", "stop_condition", "prioritized_action"):
            for text in benign + prohibited:
                with self.subTest(field=field, text=text):
                    candidate = json.loads(json.dumps(plan))
                    destination = candidate if field == "prioritized_action" else candidate["moves"][0]
                    destination[field] = text
                    failures = validate_plan_data(candidate)
                    self.assertEqual(bool(failures), text in prohibited, failures)

    def test_plural_prohibited_actions_stay_prohibited(self):
        prohibited = (
            "Begin evading the laws.",
            "Start ignoring consents.",
            "Try bypassing safeties.",
            "Ignore scopes.",
            "Start disabling safeties.",
        )
        allowed = (
            "Do not evade laws.",
            "Never ignore consents.",
            "Run a stealth pilot with consent.",
            "Work with consenting participants only.",
        )
        for text in prohibited:
            with self.subTest(text=text):
                self.assertTrue(contains_unsafe_action(text), text)
        for text in allowed:
            with self.subTest(text=text):
                self.assertFalse(contains_unsafe_action(text), text)

    def test_decimal_direction_matches_outcome_arithmetic(self):
        plan = json.loads((ROOT / "examples/bounded-plan.json").read_text(encoding="utf-8"))
        experiment = plan["moves"][0]["experiment"]
        experiment.update(baseline=1e100, target=10**100, direction="decrease")
        self.assertTrue(validate_plan_data(plan))
        experiment.update(baseline=10**100, target=1e100, direction="increase")
        self.assertTrue(validate_plan_data(plan))

    def test_json_rejects_overflow_surrogates_and_excessive_depth(self):
        for raw in ('{"a": 1e400}', '{"a": "\\ud800"}', '{"\\udfff": 1}', '[' * 65 + '0' + ']' * 65):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                load_plan_json(raw)
        self.assertEqual(load_plan_json('{"a": "\\ud83d\\ude00"}'), {"a": "\U0001f600"})

    def test_duplicate_json_key_diagnostic_does_not_echo_the_key(self) -> None:
        marker = "private_detail"
        raw = '{"private_detail": 1, "private_detail": 2}'
        with self.assertRaisesRegex(ValueError, "^JSON object contains a duplicate key$") as raised:
            load_plan_json(raw)
        self.assertNotIn(marker, str(raised.exception))

        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            plan.write_text(raw, encoding="utf-8")
            output = io.StringIO()
            with patch("sys.argv", ["validate_plan.py", str(plan)]), contextlib.redirect_stdout(output):
                self.assertEqual(validate_plan_main(), 1)

        self.assertIn("JSON object contains a duplicate key", output.getvalue())
        self.assertNotIn(marker, output.getvalue())

    def test_source_urls_are_absolute_and_credential_free(self) -> None:
        plan = json.loads((ROOT / "examples" / "example-plan.json").read_text(encoding="utf-8"))
        source = {
            "title": "Synthetic source",
            "url": "https://example.test/source",
            "supports": "A synthetic boundary.",
        }
        valid = (
            "https://example.test/source?id=1#claim",
            "http://localhost:8080/source",
            "https://[2001:db8::1]/source",
            "https://example.test/h\u00e9llo",
        )
        invalid = (
            "https://",
            "https://u@[2001:db8::1]/source",
            "https://exa mple.test/source",
            "https://exa%20mple.test/source",
            "https://example.test:invalid/source",
            "javascript:https://example.test/source",
            "https://example.test/source\nnext",
            "https://example.test\x80/source",
            "https://example.test\u200b/source",
            "https://example.test\u202e.evil.test/source",
            "https://example.test\ufeff/source",
            "https://example.test\u180e/source",
        )

        for url in valid:
            with self.subTest(url=url):
                candidate = {**plan, "sources": [{**source, "url": url}]}
                self.assertNotIn("source 1 URL must use http or https", validate_plan_data(candidate))

        for url in invalid:
            with self.subTest(url=url):
                candidate = {**plan, "sources": [{**source, "url": url}]}
                self.assertIn("source 1 URL must use http or https", validate_plan_data(candidate))

    def test_repository_json_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "schemas").mkdir()
            (root / "schemas" / "moves.schema.json").write_text(
                '{"required": ["moves"], "required": ["moves", "prioritized_action", "sources"]}\n',
                encoding="utf-8",
            )
            checker = Checker(root)
            self.assertIsNone(checker.json_file("schemas/moves.schema.json"))
            self.assertTrue(any("duplicate key" in failure for failure in checker.failures), checker.failures)
            self.assertTrue(all("prioritized_action" not in failure for failure in checker.failures))

    def test_link_outside_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "repo"
            root.mkdir()
            (parent / "outside.md").write_text("outside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[outside](../outside.md)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertIn(
                "link stays inside repo: README.md -> ../outside.md",
                checker.failures,
            )

    def test_encoded_escape_is_rejected_despite_literal_decoy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "repo"
            decoy = root / "%2e%2e"
            decoy.mkdir(parents=True)
            (decoy / "outside.md").write_text("decoy\n", encoding="utf-8")
            (parent / "outside.md").write_text("outside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[outside](%2e%2e/outside.md)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertIn(
                "link stays inside repo: README.md -> %2e%2e/outside.md",
                checker.failures,
            )

    def test_encoded_and_angle_bracket_links_with_spaces_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "My Guide.md").write_text("# Guide\n", encoding="utf-8")
            (root / "My Guide.md").write_text("# Root guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[encoded](docs/My%20Guide.md?download=1#intro)\n"
                "[angle](<My Guide.md>)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertEqual(checker.failures, [])
            self.assertEqual(
                sum(item.startswith("link exists:") for item in checker.checks),
                2,
            )

    def test_external_urls_and_same_document_anchors_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[external](https://example.test/docs/My_(Guide).md?x=1#intro)\n"
                "[anchor](#intro)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertEqual(checker.failures, [])
            self.assertEqual(checker.checks, [])

    def test_similar_prefix_sibling_is_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "repo"
            root.mkdir()
            sibling = parent / "repo-copy"
            sibling.mkdir()
            (sibling / "guide.md").write_text("outside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[outside](../repo-copy/guide.md)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertIn(
                "link stays inside repo: README.md -> ../repo-copy/guide.md",
                checker.failures,
            )

    def test_balanced_parentheses_cannot_hide_outside_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "repo"
            root.mkdir()
            (parent / "outside(foo).md").write_text("outside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[outside](../outside(foo).md)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertIn(
                "link stays inside repo: README.md -> ../outside(foo).md",
                checker.failures,
            )

    def test_escaped_parentheses_cannot_hide_outside_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "repo"
            root.mkdir()
            (parent / "outside(foo).md").write_text("outside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[outside](../outside\\(foo\\).md)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertIn(
                "link stays inside repo: README.md -> ../outside(foo).md",
                checker.failures,
            )

    def test_internal_links_with_parentheses_remain_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "inside(foo).md").write_text("inside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[balanced](docs/inside(foo).md \"Guide\")\n"
                "[escaped](docs/inside\\(foo\\).md 'Guide')\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertEqual(checker.failures, [])
            self.assertEqual(
                sum(item.startswith("link exists:") for item in checker.checks),
                2,
            )

    def test_malformed_parentheses_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[malformed](docs/inside(foo).md\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertTrue(
                any(item.startswith("link syntax is valid:") for item in checker.failures),
                checker.failures,
            )

    def test_reference_definition_outside_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "repo"
            root.mkdir()
            (parent / "outside(foo).md").write_text("outside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[outside][reference]\n\n"
                "[reference]: ../outside\\(foo\\).md \"Outside\"\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertIn(
                "link stays inside repo: README.md -> ../outside(foo).md",
                checker.failures,
            )

    def test_internal_reference_definitions_remain_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "inside(foo).md").write_text("inside\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[balanced][one]\n[angle][two]\n\n"
                "[one]: docs/inside(foo).md 'Guide'\n"
                "[two]: <docs/inside(foo).md>\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertEqual(checker.failures, [])
            self.assertEqual(
                sum(item.startswith("link exists:") for item in checker.checks),
                2,
            )

    def test_file_url_with_host_cannot_leave_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[outside](file://localhost/etc/passwd)\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertTrue(
                any(
                    item.startswith("link stays inside repo:") and "file://localhost/etc/passwd" in item
                    for item in checker.failures
                ),
                checker.failures,
            )

    def test_encoded_null_in_link_fails_closed(self) -> None:
        # NUL, another C0 control, a line feed, DEL, and a zero-width space.
        # The result must not depend on whether Path.resolve() raises, which
        # differs between Python versions.
        for encoded in ("%00", "%01", "%0a", "%7f", "%e2%80%8b"):
            with self.subTest(encoded=encoded), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(
                    f"[outside]({encoded}../outside.md)\n",
                    encoding="utf-8",
                )

                checker = Checker(root)
                checker.check_links()

                self.assertTrue(
                    any("link target is valid:" in item for item in checker.failures),
                    checker.failures,
                )
                self.assertFalse(
                    any(item.startswith("link exists:") for item in checker.checks + checker.failures),
                    checker.checks + checker.failures,
                )

    def test_virtual_environments_and_caches_are_not_scanned(self) -> None:
        # Write the dash as an escape: a literal one would fail this repository's own check.
        note = "Third-party text \u2013 [outside](../outside.md)\n"
        for skipped in ("venv/lib", ".venv/lib", "node_modules/pkg", ".pytest_cache/v", "nested/dist"):
            with self.subTest(skipped=skipped), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                folder = root / skipped
                folder.mkdir(parents=True)
                if "venv" in skipped:
                    (folder.parent / "pyvenv.cfg").write_text("home = synthetic\n", encoding="utf-8")
                (folder / "notes.md").write_text(note, encoding="utf-8")
                checker = Checker(root)
                checker.check_text_files()
                checker.check_links()
                self.assertEqual(checker.failures, [])
                self.assertFalse(any("notes.md" in item for item in checker.checks), checker.checks)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            (root / "lib" / "notes.md").write_text(note, encoding="utf-8")
            checker = Checker(root)
            checker.check_text_files()
            checker.check_links()
            self.assertIn("no em or en dash: " + str(Path("lib/notes.md")), checker.failures)
            self.assertIn("link exists: " + str(Path("lib/notes.md")) + " -> ../outside.md", checker.failures)

    def test_non_utf8_markdown_is_a_failure_not_an_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_bytes("Caf\u00e9 notes\n".encode("latin-1"))
            checker = Checker(root)
            checker.check_links()
            self.assertEqual(checker.failures, ["markdown is UTF-8: README.md"])

    def test_multiline_reference_definition_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[outside][reference]\n\n[reference]:\n  ../outside.md\n",
                encoding="utf-8",
            )

            checker = Checker(root)
            checker.check_links()

            self.assertTrue(
                any("multiline reference definition is unsupported" in item for item in checker.failures),
                checker.failures,
            )


if __name__ == "__main__":
    unittest.main()
