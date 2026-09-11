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
    def test_debrief_includes_evidence_and_escapes_authored_markup(self):
        first = {**self.first, "stop_triggered": True, "notes": '<script>synthetic</script> [link](https://example.org)'}
        rendered = moves.render_debrief(self.plan, [first, self.second])
        self.assertIn("stop_and_review", rendered)
        self.assertIn("After earlier stop: True", rendered)
        self.assertIn(moves.plan_digest(self.plan), rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("[link](", rendered)
        self.assertIn("alternative explanation", rendered)
        self.assertIn("Rollback:", rendered)
        self.assertIn("None supplied.", rendered)

    def test_new_commands_run_end_to_end_and_reject_mixed_handoff_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            plan, observation, history, bundle = [directory / name for name in ("plan.json", "observation.json", "history.json", "bundle.json")]
            plan.write_text(json.dumps(self.plan), encoding="utf-8")
            observation.write_text(json.dumps(self.first), encoding="utf-8")
            runner = fixtures.FullWorkflowTests()
            commands = [("record", plan, observation, "--output", history),
                        ("limits", plan, history), ("table", plan), ("table", plan, "--format", "csv"),
                        ("screen", plan, "--max-minutes", 20, "--exposure", "self_only", "--max-start-hours", 24, "--max-duration-hours", 48),
                        ("handoff", plan, "--timeline", history, "--output", bundle),
                        ("verify-handoff", bundle), ("debrief", plan, history, "--output", directory / "debrief.md")]
            for command in commands:
                result = runner.run_cli(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Human learning review", (directory / "debrief.md").read_text(encoding="utf-8"))
            result = runner.run_cli("handoff", plan, "--timeline", history, "--observation", observation, "--output", directory / "invalid.json")
            self.assertEqual(result.returncode, 2)
            self.assertFalse((directory / "invalid.json").exists())

    def test_whole_timeline_handoff_preserves_stops_and_detects_partial_tampering(self):
        first = {**self.first, "stop_triggered": True}
        bundle = moves.timeline_handoff(self.plan, [first, self.second])
        result = moves.verify_handoff(json.loads(json.dumps(bundle)))
        self.assertEqual(result["checkpoint_count"], 2)
        self.assertTrue(result["human_review_required"])
        self.assertEqual(bundle["timeline_review"]["decision"], "stop_and_review")
        for field in ("observations", "timeline_review", "observations_sha256"):
            bad = copy.deepcopy(bundle)
            if field == "observations":
                bad[field][0]["notes"] = "Altered synthetic note"
            elif field == "timeline_review":
                bad[field]["decision"] = "continue"
            else:
                bad[field] = "wrong"
            with self.assertRaises(ValueError):
                moves.verify_handoff(bad)
        self.assertTrue(moves.verify_handoff(moves.handoff_bundle(self.plan, self.first))["consistent"])
        oversized = {**self.first, "notes": "x" * moves.MAX_PLAN_BYTES}
        with self.assertRaisesRegex(ValueError, "byte limit"):
            moves.timeline_handoff(self.plan, [oversized])

    def test_portfolio_table_preserves_order_and_quotes_spreadsheet_text(self):
        self.plan["moves"][0]["title"] = '\n=HYPERLINK("https://example.org")'
        self.plan["moves"][0]["experiment"]["metric"] = 'Practice, "blocks"\nper day'
        rows = moves.portfolio_rows(self.plan)
        self.assertEqual([row["move_id"] for row in rows], [move["id"] for move in self.plan["moves"]])
        self.assertEqual(sum(row["selected"] for row in rows), 1)
        parsed = list(csv.DictReader(io.StringIO(moves.portfolio_csv(self.plan))))
        self.assertEqual(len(parsed), 5)
        self.assertEqual(parsed[0]["title"], "'" + rows[0]["title"])
        self.assertEqual(parsed[0]["metric"], "'" + rows[0]["metric"])
        self.assertEqual(parsed[0]["baseline"], "0")
        self.assertEqual(rows[0]["review_state"], "human_review_required")
        with self.assertRaises(ValueError):
            moves.portfolio_rows(fixtures.example())

    def test_sources_identify_repeated_citations_without_merging_distinct_paths(self):
        self.plan["sources"] = [{"title": "Synthetic language source", "url": url, "publisher": publisher,
                                  "supports": "Practice hypothesis", "date": "2026-09-10"}
                                 for url, publisher in [("https://example.org/Study#one", " Example  Publisher "),
                                    ("https://EXAMPLE.org/Study#two", "example publisher"),
                                    ("https://example.org/study", ""), ("https://example.org/Study?q=2", "")]]
        result = moves.audit_sources(self.plan, "2026-09-11", 30)
        self.assertEqual(result["repeated_url_groups"], [[1, 2]])
        self.assertEqual(result["shared_declared_publisher_groups"], [[1, 2]])
        self.assertTrue(result["independence_review_required"])
        self.assertTrue(result["human_verification_required"])
        self.assertEqual(len(result["sources"]), 4)

    def test_screen_respects_start_and_duration_without_reselection(self):
        self.plan["moves"][1]["experiment"].update(start_within_hours=0, duration_hours=1)
        result = moves.screen_moves(self.plan, 20, "self_only", 0, 1)
        self.assertEqual(result["matching_move_ids"], ["move-02"])
        self.assertEqual(result["excluded"][0]["reasons"], ["start_window_exceeds_ceiling", "duration_exceeds_ceiling"])
        self.assertEqual(self.plan["selected_move_id"], "move-01")
        self.assertEqual(len(moves.screen_moves(self.plan, 20, "self_only")["matching_move_ids"]), 5)
        for start, duration in ((-1, 1), (0, 0), (49, 1), (0, True)):
            with self.assertRaises(ValueError):
                moves.screen_moves(self.plan, 20, "self_only", start, duration)

    def test_remaining_bounds_preserve_stops_and_measure_overruns(self):
        first = {**self.first, "stop_triggered": True}
        result = moves.review_limits(self.plan, [first, self.second])
        self.assertEqual(result["bounds"]["active_minutes"]["remaining"], "12")
        self.assertEqual(result["decision"], "stop_and_review")
        last = {**self.second, "elapsed_hours": 50, "active_minutes": 21}
        result = moves.review_limits(self.plan, [first, last])
        self.assertEqual(result["bounds"]["elapsed_hours"]["overrun"], "2")
        self.assertEqual(result["bounds"]["active_minutes"]["overrun"], "1")
        self.assertEqual(result["bounds"]["active_minutes"]["remaining"], "0")
        self.assertTrue(result["bounds"]["active_minutes"]["limit_reached"])
        with self.assertRaises(ValueError):
            moves.review_limits(self.plan, [])

    def test_measurement_summary_keeps_gaps_regressions_and_stop_history(self):
        rows = [{**self.first, "elapsed_hours": index, "observed_value": value, "stop_triggered": index == 1}
                for index, value in enumerate([None, 2, None, 1, 3], 1)]
        result = moves.review_timeline(self.plan, rows)
        summary = result["measurement_summary"]
        self.assertEqual(summary["missing_checkpoints"], [1, 3])
        self.assertEqual(summary["measured_checkpoints"], 3)
        self.assertEqual(summary["first_target_checkpoint"], 2)
        self.assertEqual(summary["target_lost_checkpoints"], [4])
        self.assertTrue(summary["first_target_after_stop"])
        self.assertTrue(summary["latest_checkpoint_target_met"])
        self.assertEqual(result["decision"], "stop_and_review")
        self.plan["moves"][0]["experiment"].update(baseline=10, target=2, direction="decrease")
        for row in rows:
            row["plan_sha256"] = moves.plan_digest(self.plan)
        self.assertEqual(moves.review_timeline(self.plan, rows)["measurement_summary"]["target_lost_checkpoints"], [5])

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
