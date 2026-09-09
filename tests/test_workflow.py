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
