"""init --contract, experiments-draft, and promote move a plan from v0.1 to v0.2."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from moves import experiments_draft, plan_digest, promote_plan
from validate_plan import validate_plan_data

V01 = ROOT / "examples/example-plan.json"
V02 = ROOT / "examples/bounded-plan.json"
EXPERIMENTS = ROOT / "examples/promote-experiments.json"
SELECTION = ("--move-id", "move-01", "--reason", "Cue timing is the cheapest uncertainty to test",
             "--first-step", "Pick the existing daily cue")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(script, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


class InitContractTests(unittest.TestCase):
    def test_default_init_is_unchanged_and_v01_copies_the_free_text_example(self):
        with tempfile.TemporaryDirectory() as td:
            default, explicit, v01 = (Path(td) / name for name in ("default.json", "v02.json", "v01.json"))
            self.assertEqual(run("moves.py", "init", "--output", default).returncode, 0)
            self.assertEqual(default.read_bytes(), (json.dumps(load(V02), indent=2) + "\n").encode("utf-8"))
            self.assertEqual(run("moves.py", "init", "--contract", "v0.2", "--output", explicit).returncode, 0)
            self.assertEqual(explicit.read_bytes(), default.read_bytes())
            self.assertEqual(run("moves.py", "init", "--contract", "v0.1", "--output", v01).returncode, 0)
            self.assertEqual(v01.read_bytes(), V01.read_bytes())
            result = run("moves.py", "init", "--contract", "v0.3", "--output", Path(td) / "other.json")
            self.assertEqual(result.returncode, 2)
            self.assertFalse((Path(td) / "other.json").exists())


class ExperimentsDraftTests(unittest.TestCase):
    def test_draft_has_every_move_and_no_defaulted_number(self):
        draft = experiments_draft(load(V01))
        self.assertEqual(list(draft), [move["id"] for move in load(V01)["moves"]])
        for value in draft.values():
            self.assertEqual(set(value), set(load(EXPERIMENTS)["move-01"]))
            self.assertTrue(all(item in ("", None) for item in value.values()))

    def test_unfilled_draft_fails_promote(self):
        with self.assertRaisesRegex(ValueError, "move-01 experiment hypothesis must be non-empty text"):
            promote_plan(load(V01), experiments_draft(load(V01)), "move-01", "reason", "step")
        with tempfile.TemporaryDirectory() as td:
            draft, output = Path(td) / "experiments.json", Path(td) / "promoted.json"
            self.assertEqual(run("moves.py", "experiments-draft", V01, "--output", draft).returncode, 0)
            result = run("moves.py", "promote", V01, "--experiments", draft, *SELECTION, "--output", output)
            self.assertEqual(result.returncode, 1)
            self.assertIn("experiment baseline must be a finite number", result.stderr)
            self.assertFalse(output.exists())


class PromoteTests(unittest.TestCase):
    def test_promotion_copies_experiments_and_records_a_select_style_action(self):
        before = V01.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "promoted.json"
            result = run("moves.py", "promote", V01, "--experiments", EXPERIMENTS, *SELECTION, "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            promoted = load(output)
            self.assertEqual(V01.read_bytes(), before)
            self.assertEqual(validate_plan_data(promoted), [])
            self.assertEqual(promoted["contract_version"], "unconventional-moves/v0.2")
            self.assertEqual(promoted["selected_move_id"], "move-01")
            self.assertEqual(promoted["prioritized_action"], "Selected move-01. Reason: Cue timing is the cheapest "
                             "uncertainty to test First step: Pick the existing daily cue")
            experiments = load(EXPERIMENTS)
            original = load(V01)
            for move, source in zip(promoted["moves"], original["moves"]):
                self.assertEqual(move["experiment"], experiments[move["id"]])
                self.assertEqual({key: value for key, value in move.items() if key != "experiment"}, source)
            for key in ("goal", "high_stakes", "sources"):
                self.assertEqual(promoted[key], original[key])
            # The promoted revision supports the v0.2 workflow.
            card = json.loads(run("moves.py", "card", output).stdout)
            self.assertEqual((card["move_id"], card["plan_sha256"]), ("move-01", plan_digest(promoted)))
            draft = Path(td) / "observation.json"
            self.assertEqual(run("moves.py", "observation-draft", output, "--output", draft).returncode, 0)
            observation = load(draft)
            observation.update(elapsed_hours=24, active_minutes=10, observed_value=1, notes="Synthetic only.")
            draft.write_text(json.dumps(observation), encoding="utf-8")
            outcome = run("moves.py", "outcome", output, draft)
            self.assertEqual(outcome.returncode, 0, outcome.stderr)
            # compare reports the version change, the selection, and each new experiment.
            changes = json.loads(run("moves.py", "compare", V01, output).stdout)
            triggered = {(item["move_id"], item["field"]) for item in changes["review_triggers"]}
            self.assertIn((None, "contract_version"), triggered)
            self.assertIn((None, "selected_move_id"), triggered)
            for move_id in experiments:
                self.assertIn((move_id, "experiment"), triggered)

    def test_in_memory_promotion_never_mutates_its_inputs(self):
        plan, experiments = load(V01), load(EXPERIMENTS)
        snapshot = copy.deepcopy((plan, experiments))
        promoted = promote_plan(plan, experiments, "move-02", "Reason.", "Step.")
        self.assertEqual((plan, experiments), snapshot)
        promoted["moves"][0]["experiment"]["target"] = 99
        self.assertEqual(experiments, snapshot[1])

    def test_each_refusal_exits_1_and_creates_no_file(self):
        experiments = load(EXPERIMENTS)
        missing = {key: value for key, value in experiments.items() if key != "move-05"}
        extra = {**experiments, "move-99": experiments["move-01"]}
        not_improving = copy.deepcopy(experiments)
        not_improving["move-02"]["target"] = not_improving["move-02"]["baseline"]
        too_long = copy.deepcopy(experiments)
        too_long["move-03"].update(duration_hours=1, max_minutes=61)
        cases = {
            "missing move": (missing, SELECTION, "missing: move-05"),
            "extra move": (extra, SELECTION, "not in the plan: move-99"),
            "not an object": ([experiments["move-01"]], SELECTION, "experiments must be a JSON object keyed by move ID"),
            "target does not improve": (not_improving, SELECTION,
                                        "move-02 experiment target must improve on baseline"),
            "max minutes above duration": (too_long, SELECTION, "move-03 experiment max_minutes exceeds duration"),
            "unknown selection": (experiments, ("--move-id", "move-09", *SELECTION[2:]), "move ID must identify"),
            "blank reason": (experiments, (*SELECTION[:2], "--reason", " ", *SELECTION[4:]), "reason and first step"),
        }
        with tempfile.TemporaryDirectory() as td:
            for name, (value, selection, expected) in cases.items():
                with self.subTest(case=name):
                    path, output = Path(td) / (name + ".json"), Path(td) / (name + "-out.json")
                    path.write_text(json.dumps(value), encoding="utf-8")
                    result = run("moves.py", "promote", V01, "--experiments", path, *selection, "--output", output)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn(expected, result.stderr)
                    self.assertFalse(output.exists())
            existing = Path(td) / "existing.json"
            existing.write_text("keep", encoding="utf-8")
            result = run("moves.py", "promote", V01, "--experiments", EXPERIMENTS, *SELECTION, "--output", existing)
            self.assertEqual(result.returncode, 1)
            self.assertIn("output already exists", result.stderr)
            self.assertEqual(existing.read_text(encoding="utf-8"), "keep")

    def test_v02_input_is_refused_by_moves_and_by_the_shim(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "out.json"
            for script in ("moves.py", "moves_cli.py"):
                for args in (("promote", V02, "--experiments", EXPERIMENTS, *SELECTION),
                             ("promote", "--experiments", EXPERIMENTS, *SELECTION, V02),
                             ("experiments-draft", V02), ("experiments-draft", "--output", output, V02)):
                    with self.subTest(script=script, args=args[:2]):
                        full = args if "--output" in args else (*args, "--output", output)
                        result = run(script, *full)
                        self.assertEqual(result.returncode, 1, result.stdout)
                        expected = "requires a v0.1 plan" if script == "moves_cli.py" else "requires a version 0.1 plan"
                        self.assertIn(args[0] + " " + expected, result.stderr)
                        self.assertFalse(output.exists())
            # The shim lets a v0.1 plan through.
            self.assertEqual(run("moves_cli.py", "promote", V01, "--experiments", EXPERIMENTS, *SELECTION,
                                 "--output", output).returncode, 0)


if __name__ == "__main__":
    unittest.main()
