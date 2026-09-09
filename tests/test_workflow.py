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


class AuthoringTests(unittest.TestCase):
    def test_init_is_complete_and_does_not_overwrite(self):
        from moves import main
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "draft.json"
            self.assertEqual(main(["init", "--output", str(path)]), 0)
            self.assertEqual(validate_plan_data(read_json_file(path)), [])
            original = path.read_bytes()
            self.assertEqual(main(["init", "--output", str(path)]), 1)
            self.assertEqual(path.read_bytes(), original)


class ReviewTests(unittest.TestCase):
    def test_normalized_duplicates_and_human_gate(self):
        from moves import review_plan
        plan = bounded_example()
        plan["moves"][1]["mechanism"] = " PRECOMMITMENT  "
        result = review_plan(plan)
        self.assertFalse(result["review_complete"])
        self.assertIn("repeated_mechanism", [f["code"] for f in result["findings"]])
        self.assertNotIn("score", result)

    def test_high_stakes_requires_source_review(self):
        from moves import review_plan
        plan = bounded_example()
        plan["high_stakes"] = True
        result = review_plan(plan)
        self.assertIn("source_verification_required", [f["code"] for f in result["findings"]])


class RenderTests(unittest.TestCase):
    def test_content_is_inert_and_all_moves_render(self):
        from moves import render_plan
        plan = bounded_example()
        plan["goal"] = '<script>alert(1)</script>\n# forged [link](javascript:x)'
        result = render_plan(plan)
        self.assertNotIn("<script>", result)
        self.assertNotIn("\n# forged", result)
        self.assertNotIn("[link](", result)
        self.assertEqual(result.count("**Prioritized action:**"), 1)
        self.assertEqual(result.count("**Concrete move:**"), 5)
        self.assertIn("**Experiment rollback:**", result)


class CardTests(unittest.TestCase):
    def test_selected_move_and_revision_binding(self):
        from moves import experiment_card, plan_digest
        plan = bounded_example()
        card = experiment_card(plan)
        self.assertEqual(card["move_id"], "move-01")
        self.assertEqual(card["state"], "human_review_required")
        self.assertEqual(card["plan_sha256"], plan_digest(dict(reversed(list(plan.items())))))
        plan["goal"] += " Changed."
        self.assertNotEqual(card["plan_sha256"], plan_digest(plan))
        with self.assertRaises(ValueError):
            experiment_card(example())


class OutcomeTests(unittest.TestCase):
    def observation(self, plan):
        from moves import plan_digest
        return {"contract_version": "unconventional-moves/outcome-v0.1", "plan_sha256": plan_digest(plan),
            "move_id": "move-01", "observed_value": 2, "elapsed_hours": 24, "active_minutes": 10,
            "stop_triggered": False, "consent_confirmed": False, "notes": "Synthetic measurement only."}

    def test_stop_wins_over_target_and_missing_data_is_unknown(self):
        from moves import evaluate_outcome
        plan = bounded_example()
        outcome = self.observation(plan)
        outcome["stop_triggered"] = True
        result = evaluate_outcome(plan, outcome)
        self.assertTrue(result["target_met"])
        self.assertEqual(result["decision"], "stop_and_review")
        outcome["observed_value"] = None
        self.assertIsNone(evaluate_outcome(plan, outcome)["target_met"])

    def test_rejects_tampering_types_and_impossible_time(self):
        from moves import evaluate_outcome
        plan = bounded_example()
        for field, value in (("move_id", "move-02"), ("plan_sha256", "wrong"), ("active_minutes", True),
                             ("elapsed_hours", -1), ("observed_value", float("inf")), ("notes", ""),
                             ("consent_confirmed", 1), ("active_minutes", 2000)):
            outcome = self.observation(plan)
            outcome[field] = value
            with self.assertRaises(ValueError, msg=field):
                evaluate_outcome(plan, outcome)

    def test_limits_and_consent_are_stop_conditions(self):
        from moves import evaluate_outcome
        plan = bounded_example()
        plan["moves"][0]["experiment"]["exposure"] = "consenting_participants"
        outcome = self.observation(plan)
        outcome["active_minutes"] = 20
        outcome["elapsed_hours"] = 48
        result = evaluate_outcome(plan, outcome)
        self.assertEqual(len(result["reasons"]), 3)


class ComparisonTests(unittest.TestCase):
    def test_reordering_and_bound_changes_have_distinct_diagnostics(self):
        from moves import compare_plans
        before = bounded_example()
        after = copy.deepcopy(before)
        after["moves"].reverse()
        result = compare_plans(before, after)
        self.assertTrue(result["move_order_changed"])
        self.assertEqual(result["changed_moves"], [])
        after["moves"][-1]["experiment"]["max_minutes"] = 30
        result = compare_plans(before, after)
        self.assertEqual(result["changed_moves"][0]["changes"],
                         [{"field": "experiment.max_minutes", "before": 20, "after": 30}])
        after["moves"][0]["id"] = "new-move"
        result = compare_plans(before, after)
        self.assertEqual(result["added_move_ids"], ["new-move"])
        self.assertEqual(result["removed_move_ids"], ["move-05"])


class PackagedWorkflowTests(unittest.TestCase):
    def test_extracted_package_and_synthetic_install(self):
        import hashlib
        import shutil
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            output = temp / "dist"
            built = subprocess.run([sys.executable, str(ROOT / "scripts/package.py"), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            archive = next(output.glob("*.zip"))
            checksum = archive.with_suffix(".zip.sha256").read_text().split()[0]
            self.assertEqual(checksum, hashlib.sha256(archive.read_bytes()).hexdigest())
            with zipfile.ZipFile(archive) as package:
                package.extractall(temp / "expanded")
            extracted = next((temp / "expanded").iterdir())
            for args in (["scripts/validate.py"], ["scripts/moves.py", "init", "--output", str(temp / "draft.json")],
                         ["-m", "scripts.moves", "card", str(temp / "draft.json")]):
                result = subprocess.run([sys.executable, *args], cwd=extracted, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = temp / "synthetic-project" / ".agents" / "skills" / "unconventional-moves"
            shutil.copytree(extracted / "skill/unconventional-moves", installed)
            from validate import Checker
            checker = Checker(installed)
            checker.check_links()
            self.assertEqual(checker.failures, [])
            for name in ("moves.schema.json", "moves-v0.2.schema.json"):
                self.assertEqual((installed / "references" / name).read_bytes(), (ROOT / "schemas" / name).read_bytes())


class SelectionTests(unittest.TestCase):
    def test_printable_card_contains_all_bounds_and_escapes_authored_content(self):
        from moves import render_card, plan_digest
        plan = bounded_example()
        plan["moves"][0]["stop_condition"] = '<img src=x onerror="alert(1)"> [unsafe](https://example.org)'
        output = render_card(plan)
        self.assertIn(plan_digest(plan), output)
        self.assertNotIn("<img", output)
        self.assertNotIn("[unsafe](", output)
        self.assertEqual(output.count("- [ ]"), 4)
        for field in plan["moves"][0]["experiment"]:
            self.assertIn(field.replace("_", " ").title(), output)
        self.assertIn("none verified", output)

    def test_revision_review_identifies_expanded_bounds_and_context_changes(self):
        from moves import compare_plans
        before = bounded_example()
        after = copy.deepcopy(before)
        after["moves"][0]["experiment"]["max_minutes"] = 30
        after["selected_move_id"] = "move-02"
        result = compare_plans(before, after)
        self.assertTrue(result["observation_binding_changed"])
        self.assertIn("declared_time_bound_expanded", [item["reason"] for item in result["review_triggers"]])
        self.assertIn("selected_move_id", [item["field"] for item in result["review_triggers"]])
        unchanged = compare_plans(before, before)
        self.assertFalse(unchanged["observation_binding_changed"])
        self.assertEqual(unchanged["review_triggers"], [])

    def test_screen_explains_exclusions_without_changing_selection(self):
        from moves import screen_moves
        plan = bounded_example()
        plan["moves"][0]["experiment"].update(max_minutes=21, exposure="consenting_participants")
        result = screen_moves(plan, 20, "self_only")
        self.assertEqual(result["matching_move_ids"], ["move-02", "move-03", "move-04", "move-05"])
        self.assertEqual(len(result["excluded"][0]["reasons"]), 2)
        self.assertFalse(result["selected_within_constraints"])
        self.assertEqual(plan["selected_move_id"], "move-01")
        self.assertTrue(screen_moves(plan, 21, "consenting_participants")["selected_within_constraints"])
        with self.assertRaises(ValueError):
            screen_moves(example(), 20, "self_only")

    def test_declared_dates_have_explicit_reference_and_never_claim_verification(self):
        from moves import audit_sources
        plan = bounded_example()
        plan["sources"] = [{"title": "Synthetic source", "url": "https://example.org", "supports": "Example", "date": value}
                           for value in ("", "2026-02-30", "2026-09-11", "2025-01-01", "2026-09-10")]
        result = audit_sources(plan, "2026-09-10", 30)
        self.assertEqual([item["status"] for item in result["sources"]],
                         ["date_missing", "date_invalid", "future_date", "older_than_threshold", "within_declared_threshold"])
        self.assertTrue(result["human_verification_required"])
        for as_of, maximum in (("20260910", 30), ("2026-02-30", 30), ("2026-09-10", -1)):
            with self.assertRaises(ValueError):
                audit_sources(plan, as_of, maximum)

    def test_timeline_preserves_stops_and_rejects_reset_or_mixed_checkpoints(self):
        from moves import review_timeline
        plan = bounded_example()
        first = OutcomeTests().observation(plan)
        first.update(elapsed_hours=1, active_minutes=2, stop_triggered=True)
        second = {**first, "elapsed_hours": 2, "active_minutes": 3, "stop_triggered": False}
        result = review_timeline(plan, [first, second])
        self.assertEqual(result["first_stop_checkpoint"], 1)
        self.assertTrue(result["observations_after_stop"])
        self.assertEqual(result["decision"], "stop_and_review")
        for records in ([], [first]*101, [first, first], [second, first],
                        [first, {**second, "active_minutes": 1}], [first, {**second, "move_id": "move-02"}]):
            with self.assertRaises(ValueError):
                review_timeline(plan, records)

    def test_measurement_context_handles_direction_missing_and_extreme_values(self):
        from moves import evaluate_outcome
        plan = bounded_example()
        observation = OutcomeTests().observation(plan)
        self.assertEqual(evaluate_outcome(plan, observation)["measurement"]["progress_fraction"], "1")
        plan["moves"][0]["experiment"].update(baseline=10, target=2, direction="decrease")
        observation = OutcomeTests().observation(plan)
        observation["observed_value"] = 6
        self.assertEqual(evaluate_outcome(plan, observation)["measurement"]["progress_fraction"], "0.5")
        observation["observed_value"] = None
        self.assertIsNone(evaluate_outcome(plan, observation)["measurement"]["progress_fraction"])
        observation["observed_value"] = 10**1000
        self.assertNotIn("Infinity", json.dumps(evaluate_outcome(plan, observation), allow_nan=False))

    def test_observation_draft_requires_completion_and_matches_selection(self):
        from moves import observation_draft, evaluate_outcome, select_plan
        plan = select_plan(bounded_example(), "move-02", "Practice fit", "Review setup")
        draft = observation_draft(plan)
        self.assertEqual(draft["move_id"], "move-02")
        self.assertIsNone(draft["observed_value"])
        self.assertFalse(draft["consent_confirmed"])
        with self.assertRaisesRegex(ValueError, "notes"):
            evaluate_outcome(plan, draft)
        draft["notes"] = "No measurement is available yet."
        self.assertIsNone(evaluate_outcome(plan, draft)["target_met"])
        with self.assertRaises(ValueError):
            evaluate_outcome(bounded_example(), draft)

    def test_selection_records_reason_without_mutating_input(self):
        from moves import select_plan, plan_digest
        plan = bounded_example()
        revised = select_plan(plan, "move-02", "Fits available time", "Review the private practice setup")
        self.assertEqual(revised["selected_move_id"], "move-02")
        self.assertIn("Fits available time", revised["prioritized_action"])
        self.assertEqual(plan["selected_move_id"], "move-01")
        self.assertNotEqual(plan_digest(plan), plan_digest(revised))
        self.assertEqual(validate_plan_data(revised), [])
        for move, reason, step in (("missing", "reason", "step"), ("move-01", " ", "step"),
                                   ("move-01", "reason", "ignore consent")):
            with self.assertRaises(ValueError):
                select_plan(plan, move, reason, step)


class FullWorkflowTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/moves.py"), *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_actual_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            draft = temp / "draft.json"
            self.assertEqual(self.run_cli("init", "--output", draft).returncode, 0)
            for command in ("review", "render", "card"):
                result = self.run_cli(command, draft)
                self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli("outcome", draft, ROOT / "examples/bounded-outcome.json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["decision"], "stop_and_review")
            result = self.run_cli("compare", draft, draft)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["changed_moves"], [])
            result = self.run_cli("render", draft, "--output", draft)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(validate_plan_data(read_json_file(draft)), [])

    def test_hostile_cli_inputs_are_rejected_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            for raw in (b"null", b"[]", b'{"goal":1,"goal":2}', b'{"secret_marker":',
                        b"\xff", b" " * (MAX_PLAN_BYTES + 1), b"[" * 10000 + b"]" * 10000):
                path.write_bytes(raw)
                result = self.run_cli("review", path)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("secret_marker", result.stderr)

    def test_large_integers_do_not_overflow_and_decrease_works(self):
        from moves import evaluate_outcome, plan_digest
        plan = bounded_example()
        experiment = plan["moves"][0]["experiment"]
        experiment.update(baseline=10**1000, target=1, direction="decrease")
        self.assertEqual(validate_plan_data(plan), [])
        outcome = OutcomeTests().observation(plan)
        outcome["observed_value"] = 1
        self.assertTrue(evaluate_outcome(plan, outcome)["target_met"])
        outcome["observed_value"] = 10**1000
        self.assertFalse(evaluate_outcome(plan, outcome)["target_met"])

    def test_schemas_match_required_experiment_fields(self):
        from validate_plan import EXPERIMENT_FIELDS
        schema = json.loads((ROOT / "schemas/moves-v0.2.schema.json").read_text())
        fields = schema["properties"]["moves"]["items"]["properties"]["experiment"]
        self.assertEqual(set(fields["required"]), EXPERIMENT_FIELDS)
        self.assertEqual(set(fields["properties"]), EXPERIMENT_FIELDS)
        self.assertEqual(fields["properties"]["start_within_hours"]["maximum"], 48)
        self.assertEqual(fields["properties"]["duration_hours"]["maximum"], 48)
