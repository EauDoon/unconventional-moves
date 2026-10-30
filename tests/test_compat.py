"""Handoffs and histories written by release 0.3.0 still verify, restore, and extend."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import moves

CORPUS = ROOT / "tests/fixtures/v0.3.0"
HANDOFFS = ("plan-only.handoff.json", "observation.handoff.json", "replay.handoff.json", "precision.handoff.json")


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts/moves.py"), *map(str, args)], capture_output=True,
                          text=True, encoding="utf-8", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


class Release030CorpusTests(unittest.TestCase):
    def test_every_fixture_matches_its_recorded_digest(self):
        listed = {}
        for line in (CORPUS / "SHA256SUMS").read_text(encoding="ascii").splitlines():
            digest, name = line.split("  ")
            listed[name] = digest
        self.assertEqual(set(listed), {*HANDOFFS, "record-plan.json", "record-checkpoints.json"})
        for name, digest in listed.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((CORPUS / name).read_bytes()).hexdigest(), digest)

    def test_corpus_covers_both_handoff_versions_and_the_widened_precision(self):
        read = lambda name: moves.read_json_file(CORPUS / name)
        self.assertIsNone(read("plan-only.handoff.json")["observation"])
        self.assertEqual(read("observation.handoff.json")["outcome_review"]["measurement"]["progress_fraction"],
                         "0.04285714285714286285714285714285714")
        self.assertEqual(read("replay.handoff.json")["contract_version"], "unconventional-moves/handoff-v0.2")
        precision = read("precision.handoff.json")["timeline_review"]
        self.assertEqual(precision["checkpoints"][0]["review"]["measurement"]["progress_fraction"],
                         "-0.99999999999999999999999999999999998")
        self.assertEqual(precision["checkpoints"][1]["interval_hours"], "0.1")
        self.assertIn("consent_not_confirmed", precision["reasons"])

    def test_every_handoff_verifies_and_restores_its_exact_records(self):
        with tempfile.TemporaryDirectory() as td:
            for name in HANDOFFS:
                with self.subTest(name=name):
                    bundle = moves.read_json_file(CORPUS / name)
                    self.assertTrue(moves.verify_handoff(copy.deepcopy(bundle))["consistent"])
                    result = run("verify-handoff", CORPUS / name)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(json.loads(result.stdout)["consistent"])
                    restored = Path(td) / name
                    result = run("unpack-handoff", CORPUS / name, "--output-dir", restored)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(moves.read_json_file(restored / "plan.json"), bundle["plan"])
                    expected = (bundle["observations"] if "observations" in bundle
                                else [] if bundle["observation"] is None else [bundle["observation"]])
                    self.assertEqual(moves.read_json_file(restored / "checkpoints.json"), expected)
                    self.assertEqual((restored / "handoff.json").read_bytes(),
                                     (json.dumps(bundle, indent=2) + "\n").encode("utf-8"))

    def test_record_extends_the_stored_history(self):
        plan = moves.read_json_file(CORPUS / "record-plan.json")
        history = moves.read_json_file(CORPUS / "record-checkpoints.json")
        self.assertEqual(moves.read_json_file(CORPUS / "precision.handoff.json")["observations"], history)
        with tempfile.TemporaryDirectory() as td:
            observation = Path(td) / "next.json"
            observation.write_text(json.dumps({**history[-1], "elapsed_hours": 0.4, "active_minutes": 12,
                                               "observed_value": None}), encoding="utf-8")
            output = Path(td) / "extended.json"
            result = run("record", CORPUS / "record-plan.json", observation, "--history",
                         CORPUS / "record-checkpoints.json", "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(moves.read_json_file(output)[:2], history)
            self.assertEqual(moves.review_timeline(plan, moves.read_json_file(output))["decision"], "stop_and_review")

    def test_a_tampered_fixture_copy_yields_a_named_difference(self):
        bundle = moves.read_json_file(CORPUS / "observation.handoff.json")
        bundle["outcome_review"]["measurement"]["progress_fraction"] = "0.0428571428571428628571428571428571"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tampered.json"
            path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
            result = run("verify-handoff", path, "--diff")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual([item["path"] for item in report["mismatches"]],
                             ["outcome_review.measurement.progress_fraction"])
            self.assertEqual(report["mismatches"][0]["recomputed"], "0.04285714285714286285714285714285714")


if __name__ == "__main__":
    unittest.main()
