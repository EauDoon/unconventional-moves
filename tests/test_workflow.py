import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_plan import MAX_PLAN_BYTES, load_plan_json, read_json_file, validate_plan_data


def example():
    return json.loads((ROOT / "examples/example-plan.json").read_text())


class InputTests(unittest.TestCase):
    def test_bounded_input_and_duplicate_keys(self):
        for raw in (" " * (MAX_PLAN_BYTES + 1), '{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                load_plan_json(raw)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "large.json"
            path.write_bytes(b" " * (MAX_PLAN_BYTES + 1))
            with self.assertRaises(ValueError):
                read_json_file(path)

    def test_structured_cli_diagnostic(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_plan.py"),
                                 str(ROOT / "examples/example-plan.json"), "--json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "failures": []})


def bounded_example():
    plan = example()
    plan["contract_version"] = "unconventional-moves/v0.2"
    plan["selected_move_id"] = "move-01"
    for move in plan["moves"]:
        move["experiment"] = {"hypothesis": "Removing friction may increase completed practice blocks.",
            "metric": "completed practice blocks", "baseline": 0, "target": 2, "direction": "increase",
            "start_within_hours": 24, "duration_hours": 48, "max_minutes": 20,
            "exposure": "self_only", "rollback": "Return to the previous private practice routine."}
    return plan


class ExperimentContractTests(unittest.TestCase):
    def test_v1_and_v2_and_bounds(self):
        self.assertEqual(validate_plan_data(example()), [])
        self.assertEqual(validate_plan_data(bounded_example()), [])
        for field, bad in (("start_within_hours", 49), ("duration_hours", 0), ("max_minutes", True),
                           ("target", float("nan")), ("target", 0), ("rollback", " "), ("exposure", "public")):
            plan = bounded_example()
            plan["moves"][0]["experiment"][field] = bad
            self.assertTrue(validate_plan_data(plan), field)
        plan = bounded_example()
        plan["selected_move_id"] = "missing"
        self.assertTrue(validate_plan_data(plan))

    def test_v1_rejects_v2_fields(self):
        plan = bounded_example()
        plan["contract_version"] = "unconventional-moves/v0.1"
        self.assertTrue(validate_plan_data(plan))
