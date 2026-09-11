"""Synthetic language-practice regressions for checkpoint review."""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

import test_workflow as fixtures
import moves


class CheckpointReviewTests(unittest.TestCase):
    def test_record_validates_history_and_preserves_original(self):
        history = [self.first]
        self.assertEqual(moves.append_checkpoint(self.plan, self.second, history), [self.first, self.second])
        self.assertEqual(history, [self.first])
        for invalid in ({}, [self.second], [self.first] * 100):
            with self.assertRaises(ValueError):
                moves.append_checkpoint(self.plan, self.second, invalid)
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            plan, observation, output = [directory / name for name in ("plan.json", "observation.json", "history.json")]
            plan.write_text(json.dumps(self.plan), encoding="utf-8")
            observation.write_text(json.dumps(self.first), encoding="utf-8")
            command = ["record", str(plan), str(observation), "--output", str(output)]
            self.assertEqual(moves.main(command), 0)
            before = output.read_bytes()
            self.assertEqual(moves.main(command), 1)
            self.assertEqual(output.read_bytes(), before)

    def setUp(self):
        self.plan = fixtures.bounded_example()
        self.first = fixtures.OutcomeTests().observation(self.plan)
        self.first.update(elapsed_hours=0.2, active_minutes=2)
        self.second = {**self.first, "elapsed_hours": 0.3, "active_minutes": 8}

    def test_decimal_checkpoint_intervals_accept_exact_boundary(self):
        self.assertEqual(len(moves.review_timeline(self.plan, [self.first, self.second])["checkpoints"]), 2)
        with self.assertRaises(ValueError):
            moves.review_timeline(self.plan, [self.first, {**self.second, "active_minutes": 8.000001}])

    def test_activity_ledger_distinguishes_idle_and_full_intervals(self):
        observations = [self.first, self.second, {**self.second, "elapsed_hours": 1}]
        rows = moves.review_timeline(self.plan, observations)["checkpoints"]
        self.assertEqual(rows[1]["interval_active_minutes"], "6")
        self.assertEqual(rows[1]["interval_hours"], "0.1")
        self.assertEqual(rows[1]["interval_activity_fraction"], "1")
        self.assertEqual(Decimal(rows[2]["interval_activity_fraction"]), 0)
        zero = {**self.first, "elapsed_hours": 0, "active_minutes": 0}
        self.assertIsNone(moves.review_timeline(self.plan, [zero])["checkpoints"][0]["interval_activity_fraction"])
