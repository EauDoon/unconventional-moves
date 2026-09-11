import contextlib
import io
import json
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
        )
        invalid = (
            "https://",
            "https://u@[2001:db8::1]/source",
            "https://exa mple.test/source",
            "https://exa%20mple.test/source",
            "https://example.test:invalid/source",
            "javascript:https://example.test/source",
            "https://example.test/source\nnext",
        )

        for url in valid:
            with self.subTest(url=url):
                candidate = {**plan, "sources": [{**source, "url": url}]}
                self.assertNotIn("source 1 URL must use http or https", validate_plan_data(candidate))

        for url in invalid:
            with self.subTest(url=url):
                candidate = {**plan, "sources": [{**source, "url": url}]}
                self.assertIn("source 1 URL must use http or https", validate_plan_data(candidate))

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
