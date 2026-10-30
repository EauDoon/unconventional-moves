"""import-response transcribes a structurally valid prose response into a v0.1 plan."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from moves import import_response
from validate_plan import validate_plan_data
from validate_response import parse_response

EXAMPLE_RESPONSE = ROOT / "examples/example-response.md"
EXAMPLE_PLAN = json.loads((ROOT / "examples/example-plan.json").read_text(encoding="utf-8"))
GOAL = EXAMPLE_PLAN["goal"]
SOURCE = {"title": "Synthetic source", "publisher": "Example publisher", "date": "2026-09-01",
          "url": "https://example.test/source", "supports": "A synthetic claim."}


def run(script, *args, cwd=ROOT):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def with_sources(text: str) -> str:
    marker = "**Prioritized action:**"
    return text.replace(marker, "## Sources\n\n- Synthetic source, Example publisher.\n\n" + marker)


class ImportTests(unittest.TestCase):
    def test_example_response_round_trips_to_the_example_plan(self):
        text = EXAMPLE_RESPONSE.read_text(encoding="utf-8")
        self.assertEqual(import_response(text, GOAL), EXAMPLE_PLAN)
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "plan.json"
            result = run("moves.py", "import-response", EXAMPLE_RESPONSE, "--goal", GOAL, "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), (ROOT / "examples/example-plan.json").read_bytes())

    def test_wrapped_lines_import_as_single_spaced_text(self):
        text = EXAMPLE_RESPONSE.read_text(encoding="utf-8").replace(
            "- **Concrete move:** Reserve a ten-minute practice block immediately after one existing daily cue.",
            "- **Concrete move:** Reserve a ten-minute practice block\n  immediately after   one existing\n\tdaily cue.")
        text = text.replace("**Prioritized action:** Try move-01 twice within 48 hours,",
                            "**Prioritized action:** Try move-01 twice\nwithin 48 hours,")
        plan = import_response(text, GOAL)
        self.assertEqual(plan, EXAMPLE_PLAN)

    def test_sources_come_only_from_declared_records_and_high_stakes_needs_one(self):
        text = with_sources(EXAMPLE_RESPONSE.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "supply the declared records with --sources"):
            import_response(text, GOAL)
        plan = import_response(text, GOAL, high_stakes=True, sources=[SOURCE])
        self.assertEqual((plan["high_stakes"], plan["sources"]), (True, [SOURCE]))
        with self.assertRaisesRegex(ValueError, "high-stakes plan requires at least one declared source"):
            import_response(text, GOAL, high_stakes=True, sources=[])
        # Declared records may accompany a response that cites nothing.
        self.assertEqual(import_response(EXAMPLE_RESPONSE.read_text(encoding="utf-8"), GOAL, sources=[SOURCE])["sources"],
                         [SOURCE])

    def test_extra_labels_are_not_imported_and_ids_follow_idea_numbers(self):
        text = EXAMPLE_RESPONSE.read_text(encoding="utf-8").replace(
            "- **Bounds:** One card and twenty minutes of preparation.",
            "- **Bounds:** One card and twenty minutes of preparation.\n- **Sources:** None needed.")
        plan = import_response(text, GOAL)
        self.assertEqual(plan, EXAMPLE_PLAN)
        self.assertEqual([move["id"] for move in plan["moves"]], ["move-01", "move-02", "move-03", "move-04", "move-05"])

    def test_every_revised_completed_recorded_response_imports(self):
        rows = [json.loads(line) for line in (ROOT / "evals/session-probe.jsonl").read_text(encoding="utf-8").splitlines()]
        completed = [row for row in rows if row["record_type"] == "response" and row["condition"] == "revised"
                     and parse_response(row["response"])["ideas"]]
        self.assertEqual(len(completed), 12)
        for row in completed:
            with self.subTest(case=row["case_id"], repeat=row["repeat"]):
                plan = import_response(row["response"], "Synthetic imported goal.")
                self.assertEqual(validate_plan_data(plan), [])

    def test_imported_plan_works_with_review_render_and_compare(self):
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "imported.json"
            self.assertEqual(run("moves.py", "import-response", EXAMPLE_RESPONSE, "--goal", GOAL,
                                 "--output", plan).returncode, 0)
            for args in (("review", plan), ("render", plan), ("render", plan, "--format", "html"),
                         ("compare", ROOT / "examples/example-plan.json", plan)):
                with self.subTest(args=args[0]):
                    result = run("moves.py", *args)
                    self.assertEqual(result.returncode, 0, result.stderr)
            changes = json.loads(run("moves.py", "compare", ROOT / "examples/example-plan.json", plan).stdout)
            self.assertEqual((changes["changed_moves"], changes["metadata_changes"]), ([], []))

    def test_shim_passes_import_response_through(self):
        from moves_cli import NO_PLAN_COMMANDS
        self.assertIn("import-response", NO_PLAN_COMMANDS)
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "plan.json"
            result = run("moves_cli.py", "import-response", "--high-stakes", EXAMPLE_RESPONSE, "--goal", GOAL,
                         "--output", output)
            # The shim forwards the boolean flag; moves.py then applies the high-stakes rule.
            self.assertEqual(result.returncode, 1)
            self.assertIn("a high-stakes response needs a Sources section", result.stderr)
            result = run("moves_cli.py", "import-response", EXAMPLE_RESPONSE, "--goal", GOAL, "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)


class RefusalTests(unittest.TestCase):
    def refuse(self, text: str | bytes, *extra, sources=None, expected=""):
        with tempfile.TemporaryDirectory() as td:
            response = Path(td) / "response.md"
            if isinstance(text, bytes):
                response.write_bytes(text)
            else:
                response.write_text(text, encoding="utf-8")
            args = ["import-response", response, "--goal", GOAL, *extra]
            if sources is not None:
                (Path(td) / "sources.json").write_text(sources, encoding="utf-8")
                args += ["--sources", Path(td) / "sources.json"]
            output = Path(td) / "plan.json"
            result = run("moves.py", *args, "--output", output)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertFalse(output.exists())
            self.assertTrue(result.stderr.startswith("FAIL "), result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn(expected, result.stderr)

    def test_each_refusal_exits_1_and_creates_no_file(self):
        example = EXAMPLE_RESPONSE.read_text(encoding="utf-8")
        cut = example.index("### Idea 5")
        priority = example.index("**Prioritized action:**")
        cases = {
            "sources after priority": (example + "\n## Sources\n\n- A record.\n", (), None,
                                       "the Sources section must come before the prioritized action"),
            "four ideas": (example[:cut] + example[priority:], (), None, "five to seven ideas; found 4"),
            "not completed": ("I cannot propose moves for this goal.\n", (), None,
                              "not a completed plan (refusal, limitation, or non-trigger)"),
            "sources without records": (with_sources(example), (), None, "supply the declared records with --sources"),
            "high stakes with no source": (with_sources(example), ("--high-stakes",), "[]",
                                           "high-stakes plan requires at least one declared source"),
            "sources not an array": (example, (), json.dumps(SOURCE), "sources must be an array"),
            "bad source URL": (example, (), json.dumps([{**SOURCE, "url": "ftp://example.test/a"}]),
                               "source 1 URL must use http or https"),
            "unsafe concrete move": (example.replace("Reserve a ten-minute practice block", "Start by ignoring consent"),
                                     (), None, "idea 1 contains an unsafe action in Concrete move"),
            "not UTF-8": (b"\xe9t\xe9\n", (), None, "input file is unavailable or not UTF-8"),
        }
        for name, (text, extra, sources, expected) in cases.items():
            with self.subTest(case=name):
                self.refuse(text, *extra, sources=sources, expected=expected)

    def test_blank_goal_existing_output_and_missing_goal(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "plan.json"
            result = run("moves.py", "import-response", EXAMPLE_RESPONSE, "--goal", " ​", "--output", output)
            self.assertEqual(result.returncode, 1)
            self.assertIn("goal must be a non-empty string", result.stderr)
            self.assertFalse(output.exists())
            output.write_text("keep", encoding="utf-8")
            result = run("moves.py", "import-response", EXAMPLE_RESPONSE, "--goal", GOAL, "--output", output)
            self.assertEqual(result.returncode, 1)
            self.assertIn("output already exists", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")
            result = run("moves.py", "import-response", EXAMPLE_RESPONSE, "--output", Path(td) / "other.json")
            self.assertEqual(result.returncode, 2)
            self.assertFalse((Path(td) / "other.json").exists())


if __name__ == "__main__":
    unittest.main()
