"""Synthetic language-practice regressions for checkpoint review."""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

import test_workflow as fixtures
import moves


class CheckpointReviewTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixtures.bounded_example()
        self.first = fixtures.OutcomeTests().observation(self.plan)
        self.first.update(elapsed_hours=0.2, active_minutes=2)
        self.second = {**self.first, "elapsed_hours": 0.3, "active_minutes": 8}

    def test_decimal_checkpoint_intervals_accept_exact_boundary(self):
        self.assertEqual(len(moves.review_timeline(self.plan, [self.first, self.second])["checkpoints"]), 2)
        with self.assertRaises(ValueError):
            moves.review_timeline(self.plan, [self.first, {**self.second, "active_minutes": 8.000001}])
