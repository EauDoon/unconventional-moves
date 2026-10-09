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
    def test_text_diagnostics_escape_authored_fields_and_versions(self):
        injected = 'invalid\nPASS valid plan\x1b[2J'
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'plan.json'
            for document, commands in (
                ({**example(), injected: True}, (
                    ('scripts/validate_plan.py',), ('scripts/moves.py', 'review'),
                    ('scripts/moves_cli.py', 'review'))),
                ({**example(), 'contract_version': injected}, (
                    ('scripts/moves_cli.py', 'review'),)),
            ):
                path.write_text(json.dumps(document), encoding='utf-8')
                for command in commands:
                    with self.subTest(command=command):
                        result = subprocess.run([sys.executable, *command, str(path)],
                                                cwd=ROOT, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 1)
                        diagnostic = result.stdout + result.stderr
                        self.assertEqual(len(diagnostic.splitlines()), 1)
                        self.assertTrue(diagnostic.startswith('FAIL '))
                        self.assertNotIn('\x1b', diagnostic)
                        self.assertIn(json.dumps(injected)[1:-1], diagnostic)

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

    def test_invisible_characters_do_not_satisfy_required_text(self):
        from moves import evaluate_outcome, select_plan
        invisible = "\u200b\ufeff\u2060"
        plan = example()
        plan["goal"] = invisible
        self.assertIn("goal must be a non-empty string", validate_plan_data(plan))
        plan = example()
        plan["goal"] = " "
        self.assertIn("goal must be a non-empty string", validate_plan_data(plan))
        plan = example()
        plan["goal"] = "Practice\u200c blocks"
        self.assertNotIn("goal must be a non-empty string", validate_plan_data(plan))
        plan = example()
        plan["prioritized_action"] = invisible
        self.assertIn("prioritized_action must be one non-empty string", validate_plan_data(plan))
        plan = example()
        plan["moves"][0]["concrete_move"] = "\u200b"
        self.assertTrue(any("concrete_move" in failure for failure in validate_plan_data(plan)))
        plan = example()
        plan["sources"] = [{"title": "\ufeff", "url": "https://example.test/source", "supports": "A declared boundary."}]
        self.assertTrue(any("title" in failure for failure in validate_plan_data(plan)))
        plan["sources"][0]["title"] = "Synthetic source"
        plan["sources"][0]["supports"] = "\ufeff"
        self.assertTrue(any("supports" in failure for failure in validate_plan_data(plan)))
        plan = bounded_example()
        plan["moves"][0]["experiment"]["hypothesis"] = "\u200b"
        self.assertTrue(any("hypothesis" in failure for failure in validate_plan_data(plan)))
        plan = bounded_example()
        outcome = OutcomeTests().observation(plan)
        outcome["notes"] = invisible
        with self.assertRaisesRegex(ValueError, "notes"):
            evaluate_outcome(plan, outcome)
        with self.assertRaisesRegex(ValueError, "non-empty"):
            select_plan(plan, "move-02", invisible, "Review the private setup")
        with self.assertRaisesRegex(ValueError, "non-empty"):
            select_plan(plan, "move-02", "Fits the available window", "\u200b")


class AuthoringTests(unittest.TestCase):
    def test_unencodable_output_does_not_create_an_empty_artifact(self):
        from moves import emit
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "review.md"
            with self.assertRaises(UnicodeEncodeError):
                emit("Invalid Unicode: \ud800", path)
            self.assertFalse(path.exists())

    def test_failed_write_does_not_leave_a_partial_artifact(self):
        from unittest.mock import patch
        from moves import emit
        for failure in ('write', 'close'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as td:
                path = Path(td) / "review.md"
                real_open = Path.open

                def failing_open(target, mode="r", *args, **kwargs):
                    handle = real_open(target, mode, *args, **kwargs)
                    if target == path:
                        original = getattr(handle, failure)

                        def boom(*arguments):
                            if failure == 'write':
                                original(arguments[0][:1])
                            else:
                                original()
                            raise OSError("synthetic disk failure")

                        setattr(handle, failure, boom)
                    return handle

                with patch.object(Path, "open", failing_open):
                    with self.assertRaises(OSError):
                        emit("complete report\n", path)
                self.assertFalse(path.exists())

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

    def test_documented_evidence_plurals_are_recognized(self):
        from moves import review_plan
        plan = bounded_example()
        plan["moves"][0]["evidence_status"] = "Supplied facts."
        plan["moves"][1]["evidence_status"] = "Checked facts only."
        plan["moves"][2]["evidence_status"] = "The sources were not opened."
        plan["moves"][3]["evidence_status"] = "factory setting"
        unclear = [item["move_id"] for item in review_plan(plan)["findings"]
                   if item["code"] == "evidence_label_unclear"]
        self.assertEqual(unclear, ["move-04"])


class RenderTests(unittest.TestCase):
    def test_priority_is_last_and_declared_selection_is_not_human_approval(self):
        from moves import render_plan, render_html, render_card, experiment_card, observation_draft
        plan = bounded_example()
        plan["selected_move_id"] = "move-02"
        plan["prioritized_action"] = "Start move-01 instead."
        # Free-text disagreement stays valid for semantic review, never rebinding the card.
        self.assertEqual(validate_plan_data(plan), [])
        markdown = render_plan(plan)
        rendered = render_html(plan)
        for output in (markdown, rendered, render_card(plan)):
            self.assertIn("semantic alignment is not validated", output)
            self.assertNotIn("Human-selected", output)
        self.assertIn("**Declared selected move:** move\\-02", markdown)
        self.assertIn("Declared selected move: move-02", rendered)
        self.assertLess(markdown.index("## Sources"), markdown.index("**Prioritized action:**"))
        self.assertTrue(markdown.rstrip().endswith("Start move\\-01 instead\\."))
        self.assertTrue(render_card(plan).rstrip().endswith("Start move\\-01 instead\\."))
        self.assertLess(rendered.index("<h2>Declared sources</h2>"), rendered.index("<h2>Recorded priority</h2>"))
        self.assertEqual(experiment_card(plan)["move_id"], "move-02")
        self.assertEqual(observation_draft(plan)["move_id"], "move-02")
        legacy = render_plan(example())
        self.assertNotIn("Declared selected move", legacy)
        self.assertLess(legacy.index("## Sources"), legacy.index("**Prioritized action:**"))

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
    def test_numeric_representation_changes_are_visible_when_binding_changes(self):
        from moves import compare_plans, plan_digest
        for field, old, new in (("baseline", 0, 0.0), ("baseline", 0.0, -0.0),
                                ("target", 2, 2.0), ("target", 10**100, 1e100)):
            with self.subTest(field=field, old=old, new=new):
                before = bounded_example()
                before["moves"][0]["experiment"][field] = old
                after = copy.deepcopy(before)
                after["moves"][0]["experiment"][field] = new
                self.assertEqual(validate_plan_data(before), [])
                self.assertEqual(validate_plan_data(after), [])
                result = compare_plans(before, after)
                self.assertNotEqual(plan_digest(before), plan_digest(after))
                self.assertTrue(result["observation_binding_changed"])
                self.assertEqual(len(result["changed_moves"]), 1)
                changes = result["changed_moves"][0]["changes"]
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0]["field"], "experiment." + field)
                self.assertEqual(json.dumps(changes[0]["before"]), json.dumps(old))
                self.assertEqual(json.dumps(changes[0]["after"]), json.dumps(new))
                self.assertIn("experiment." + field, [item["field"] for item in result["review_triggers"]])

    def test_object_key_order_does_not_create_revision_changes(self):
        from moves import compare_plans
        before = bounded_example()
        after = copy.deepcopy(before)
        after["moves"][0]["experiment"] = dict(reversed(list(after["moves"][0]["experiment"].items())))
        after = dict(reversed(list(after.items())))
        result = compare_plans(before, after)
        self.assertFalse(result["observation_binding_changed"])
        self.assertEqual(result["changed_moves"], [])
        self.assertEqual(result["metadata_changes"], [])
        self.assertEqual(result["review_triggers"], [])

    def test_strategy_and_test_revisions_require_review_in_both_contracts(self):
        from moves import compare_plans
        for make_plan in (example, bounded_example):
            for field in ("mechanism", "test_48h", "why_overlooked"):
                with self.subTest(contract=make_plan.__name__, field=field):
                    before = make_plan()
                    after = copy.deepcopy(before)
                    after["moves"][0][field] = "Revised synthetic private practice approach."
                    result = compare_plans(before, after)
                    self.assertEqual([item["field"] for item in result["review_triggers"]], [field])
                    self.assertEqual(result["review_triggers"][0]["move_id"], "move-01")

    def test_adding_or_removing_the_experiment_object_requires_review(self):
        from moves import compare_plans
        full = bounded_example()
        plain = copy.deepcopy(full)
        for move in plain["moves"]:
            move.pop("experiment")
        plain.pop("selected_move_id")
        plain["contract_version"] = "unconventional-moves/v0.1"
        self.assertEqual(validate_plan_data(full), [])
        self.assertEqual(validate_plan_data(plain), [])
        for before, after in ((plain, full), (full, plain)):
            with self.subTest(direction=after["contract_version"]):
                result = compare_plans(before, after)
                experiment_triggers = [item for item in result["review_triggers"] if item["field"] == "experiment"]
                self.assertEqual(len(experiment_triggers), 5)
                self.assertTrue(all(item["reason"] == "experiment_or_review_condition_changed" for item in experiment_triggers))
                self.assertEqual({item["move_id"] for item in experiment_triggers}, {f"move-0{index}" for index in range(1, 6)})

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


    def test_adding_or_removing_a_move_is_not_a_reorder(self):
        from moves import compare_plans
        before = bounded_example()
        appended = copy.deepcopy(before)
        appended["moves"].append(dict(copy.deepcopy(before["moves"][0]), id="move-06"))
        self.assertEqual(validate_plan_data(appended), [])
        result = compare_plans(before, appended)
        self.assertEqual(result["added_move_ids"], ["move-06"])
        self.assertFalse(result["move_order_changed"])
        self.assertTrue(result["observation_binding_changed"])
        removed = copy.deepcopy(before)
        removed["moves"] = [move for move in removed["moves"] if move["id"] != "move-05"]
        removed["moves"].append(dict(copy.deepcopy(before["moves"][0]), id="move-07"))
        result = compare_plans(before, removed)
        self.assertEqual(result["removed_move_ids"], ["move-05"])
        self.assertFalse(result["move_order_changed"])
        swapped = copy.deepcopy(appended)
        swapped["moves"][1], swapped["moves"][2] = swapped["moves"][2], swapped["moves"][1]
        self.assertTrue(compare_plans(before, swapped)["move_order_changed"])


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
                         ["-m", "scripts.moves", "card", str(temp / "draft.json"), "--format", "markdown"],
                         ["scripts/moves.py", "render", str(temp / "draft.json"), "--format", "html"],
                         ["scripts/moves.py", "handoff", str(temp / "draft.json"), "--output", str(temp / "handoff.json")],
                         ["scripts/moves.py", "verify-handoff", str(temp / "handoff.json")]):
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
    def test_portable_handoff_recomputes_every_claim_and_caps_actual_bytes(self):
        from moves import handoff_bundle, verify_handoff
        plan = bounded_example()
        bundle = handoff_bundle(plan, OutcomeTests().observation(plan))
        self.assertTrue(verify_handoff(json.loads(json.dumps(bundle)))["consistent"])
        for section, field, value in (("plan", "goal", "Changed goal"), ("card", "state", "approved"),
                                     ("review", "review_complete", True), ("outcome_review", "target_met", 1)):
            bad = copy.deepcopy(bundle)
            bad[section][field] = value
            with self.assertRaises(ValueError):
                verify_handoff(bad)
        for invalid in (None, [], {**bundle, "extra": True}):
            with self.assertRaises(ValueError):
                verify_handoff(invalid)
        plan["goal"] = "x" * (MAX_PLAN_BYTES // 2)
        with self.assertRaisesRegex(ValueError, "byte limit"):
            handoff_bundle(plan)

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
                        [first, {**second, "active_minutes": 1}], [first, {**second, "move_id": "move-02"}],
                        [first, {**second, "elapsed_hours": 1.01, "active_minutes": 5}]):
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
        from decimal import Decimal, localcontext
        from moves import plan_digest
        plan["moves"][0]["experiment"].update(baseline=10**1000, target=1, direction="decrease")
        observation = OutcomeTests().observation(plan)
        observation["observed_value"] = 10**500
        observation["plan_sha256"] = plan_digest(plan)
        review = evaluate_outcome(plan, observation)
        self.assertIs(review["target_met"], False)
        measurement = review["measurement"]
        with localcontext() as context:
            context.prec = 2000
            expected_change = Decimal(10**500) - Decimal(10**1000)
        self.assertEqual(Decimal(measurement["change_from_baseline"]), expected_change)
        self.assertLess(Decimal(measurement["progress_fraction"]), Decimal(1))
        self.assertNotIn("Infinity", json.dumps(review, allow_nan=False))

    def test_progress_stays_exact_when_operand_magnitudes_differ(self):
        # Compare Decimal values: an inexact quotient may carry trailing zeros.
        from decimal import Decimal
        from moves import evaluate_outcome, plan_digest
        for baseline, target, direction, observed, expected_met in (
                (1e30, 1e-5, "decrease", 2e-5, False),
                (-1e40, 1e-12, "increase", 2e-12, True)):
            with self.subTest(baseline=baseline, target=target):
                plan = bounded_example()
                plan["moves"][0]["experiment"].update(baseline=baseline, target=target, direction=direction)
                self.assertEqual(validate_plan_data(plan), [])
                observation = OutcomeTests().observation(plan)
                observation.update(observed_value=observed, plan_sha256=plan_digest(plan))
                review = evaluate_outcome(plan, observation)
                self.assertIs(review["target_met"], expected_met)
                progress = Decimal(review["measurement"]["progress_fraction"])
                # A fraction of exactly 1 would claim the observed value is the target.
                self.assertNotEqual(progress, 1)
                self.assertEqual(progress > 1, expected_met)
                if direction == "decrease":
                    self.assertEqual(Decimal(review["measurement"]["change_from_baseline"]),
                                     Decimal("-999999999999999999999999999999.99998"))

    def test_progress_strings_match_earlier_releases_when_their_arithmetic_was_exact(self):
        # verify-handoff recomputes these strings and requires an exact match,
        # so bundles written by 0.2.0 must keep the same digits. The expected
        # strings are what 0.2.0 produced for the same inputs.
        from moves import measurement_context
        experiment = bounded_example()["moves"][0]["experiment"]
        for target, observed, change, progress in (
                (7, 0.1 + 0.2, "0.30000000000000004", "0.04285714285714286285714285714285714"),
                (7, 1e30, "1000000000000000000000000000000", "142857142857142857142857142857.1")):
            with self.subTest(observed=observed):
                measurement = measurement_context({**experiment, "baseline": 0, "target": target}, observed)
                self.assertEqual(measurement["change_from_baseline"], change)
                self.assertEqual(measurement["progress_fraction"], progress)

    def test_progress_widens_when_earlier_precision_would_display_one(self):
        # 0.2.0 rounded this fraction to 1.000000000000000000000000000, which
        # claimed the observed value was the target.
        from decimal import Decimal
        from moves import measurement_context
        experiment = {**bounded_example()["moves"][0]["experiment"],
                      "baseline": 0, "target": 5000000000000000000000000001}
        measurement = measurement_context(experiment, 5000000000000000000000000002)
        self.assertEqual(measurement["change_from_baseline"], "5000000000000000000000000002")
        self.assertEqual(measurement["progress_fraction"], "1.000000000000000000000000000200")
        self.assertGreater(Decimal(measurement["progress_fraction"]), 1)

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
        with self.assertRaisesRegex(ValueError, "byte limit"):
            select_plan(plan, "move-01", "x" * MAX_PLAN_BYTES, "Review setup")
        for move, reason, step in (("missing", "reason", "step"), ("move-01", " ", "step"),
                                   ("move-01", "reason", "ignore consent")):
            with self.assertRaises(ValueError):
                select_plan(plan, move, reason, step)


class FullWorkflowTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/moves.py"), *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_handoff_rejects_supplied_null_observation_without_creating_output(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            observation, bundle = temp / "observation.json", temp / "handoff.json"
            observation.write_text("null\n", encoding="utf-8")
            result = self.run_cli("handoff", ROOT / "examples/bounded-plan.json",
                                  "--observation", observation, "--output", bundle)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("observation must be an object", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(bundle.exists())
            self.assertEqual(observation.read_text(encoding="utf-8"), "null\n")
            # Omitting the argument still creates a compatible plan-only handoff.
            result = self.run_cli("handoff", ROOT / "examples/bounded-plan.json", "--output", bundle)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(read_json_file(bundle)["observation"])
            result = self.run_cli("verify-handoff", bundle)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["observation_present"])

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

    def test_complete_second_release_cli_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            plan, selected, observation, bundle = [temp / name for name in ("plan.json", "selected.json", "observation.json", "handoff.json")]
            commands = [("init", "--output", plan),
                        ("select", plan, "--move-id", "move-02", "--reason", "Fits practice time", "--first-step", "Review private setup", "--output", selected),
                        ("observation-draft", selected, "--output", observation)]
            for command in commands:
                result = self.run_cli(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
            data = read_json_file(observation)
            data.update(notes="Synthetic checkpoint, measurement unavailable.", elapsed_hours=1)
            observation.write_text(json.dumps(data), encoding="utf-8")
            checkpoints = temp / "checkpoints.json"
            checkpoints.write_text(json.dumps([data]), encoding="utf-8")
            for command in (("outcome", selected, observation), ("timeline", selected, checkpoints),
                            ("screen", selected, "--max-minutes", "20", "--exposure", "self_only"),
                            ("sources", selected, "--as-of", "2026-09-10", "--max-age-days", "30"),
                            ("compare", plan, selected), ("card", selected, "--format", "markdown"),
                            ("handoff", selected, "--observation", observation, "--output", bundle),
                            ("verify-handoff", bundle), ("render", selected, "--format", "html", "--output", temp / "review.html")):
                result = self.run_cli(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Declared selection", (temp / "review.html").read_text())
            self.assertEqual(self.run_cli("handoff", selected, "--output", bundle).returncode, 1)

    def test_html_export_is_inert_and_keeps_all_contract_fields(self):
        from html.parser import HTMLParser
        from moves import render_html
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, dict(attrs)))
        plan = bounded_example()
        plan["goal"] = '<script>alert("synthetic")</script>'
        plan["moves"][0]["title"] = '" onclick="alert(1)'
        rendered = render_html(plan)
        parser = Tags()
        parser.feed(rendered)
        self.assertFalse(any(tag in {"script", "img", "iframe", "form", "input"} for tag, _ in parser.tags))
        self.assertEqual(sum(tag == "article" for tag, _ in parser.tags), 5)
        for tag, attrs in parser.tags:
            self.assertFalse(any(key.startswith("on") for key in attrs))
            if tag == "a":
                self.assertTrue(attrs["href"].startswith("#"))
        self.assertIn("Content-Security-Policy", rendered)
        self.assertIn("Declared selection", rendered)
        self.assertNotIn("Human-selected", rendered)
        self.assertIn("Rollback", rendered)

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

    def test_invalid_argument_values_exit_2_at_parse_time(self):
        plan = ROOT / "examples/bounded-plan.json"
        screen = ("screen", plan, "--exposure", "self_only")
        for args in (
            (*screen, "--max-minutes", "0"),
            (*screen, "--max-minutes", "2881"),
            (*screen, "--max-minutes", "\uff15"),
            (*screen, "--max-minutes", "20", "--max-start-hours", "99"),
            (*screen, "--max-minutes", "20", "--max-duration-hours", "0"),
            ("sources", plan, "--as-of", "2026-02-30", "--max-age-days", "30"),
            ("sources", plan, "--as-of", "\uff12\uff10\uff12\uff16-09-10", "--max-age-days", "30"),
            ("sources", plan, "--as-of", "2026-09-10", "--max-age-days", "-1"),
        ):
            with self.subTest(args=args[2:]):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("usage:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        # Boundary values remain accepted.
        for args in ((*screen, "--max-minutes", "2880", "--max-start-hours", "0", "--max-duration-hours", "48"),
                     ("sources", plan, "--as-of", "2026-09-10", "--max-age-days", "0")):
            with self.subTest(args=args[2:]):
                self.assertEqual(self.run_cli(*args).returncode, 0)

    def test_file_errors_name_the_input_or_the_output(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            result = self.run_cli("review", ROOT / "examples/bounded-plan.json",
                                  "--output", temp / "missing-directory" / "review.json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL output could not be created", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            result = self.run_cli("review", temp / "missing.json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL input file is unavailable", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            existing = temp / "existing.json"
            existing.write_text("{}", encoding="utf-8")
            result = self.run_cli("review", ROOT / "examples/bounded-plan.json", "--output", existing)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL output already exists", result.stderr)

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

    def test_published_schemas_agree_with_the_python_validator(self):
        from validate_plan import MOVE_FIELDS, SOURCE_FIELDS, TOP_LEVEL_FIELDS
        for filename, version in (("moves.schema.json", "unconventional-moves/v0.1"),
                                  ("moves-v0.2.schema.json", "unconventional-moves/v0.2")):
            with self.subTest(schema=filename):
                schema = json.loads((ROOT / "schemas" / filename).read_text())
                moves = schema["properties"]["moves"]
                sources = schema["properties"]["sources"]["items"]
                top = set(TOP_LEVEL_FIELDS) | ({"selected_move_id"} if version.endswith("v0.2") else set())
                move = set(MOVE_FIELDS) | ({"experiment"} if version.endswith("v0.2") else set())
                self.assertEqual(set(schema["required"]), top)
                self.assertEqual(set(schema["properties"]), top)
                self.assertEqual(set(moves["items"]["required"]), move)
                self.assertEqual(set(moves["items"]["properties"]), move)
                self.assertEqual((moves["minItems"], moves["maxItems"]), (5, 7))
                self.assertEqual(set(sources["properties"]), SOURCE_FIELDS)
                self.assertEqual(set(sources["required"]), set(SOURCE_FIELDS) - {"publisher", "date"})

    def test_schema_move_count_bounds_match_the_validator(self):
        for filename in ("moves.schema.json", "moves-v0.2.schema.json"):
            moves = json.loads((ROOT / "schemas" / filename).read_text())["properties"]["moves"]
            low, high = moves["minItems"], moves["maxItems"]
            counts = list(range(1, low)) + list(range(low, high + 1)) + list(range(high + 1, high + 3))
            for count in counts:
                plan = bounded_example()
                plan["moves"] = [dict(plan["moves"][0], id=f"move-{index:02d}") for index in range(1, count + 1)]
                plan["selected_move_id"] = "move-01"
                rejected = "moves must contain five to seven entries" in validate_plan_data(plan)
                with self.subTest(schema=filename, moves=count):
                    self.assertEqual(rejected, not low <= count <= high)


class CheckRunnerTests(unittest.TestCase):
    """Never run the full check.py here: its unit-test step would recurse."""

    def test_list_prints_the_ci_check_set_in_order(self):
        from check import CHECKS, describe
        result = subprocess.run([sys.executable, str(ROOT / "scripts/check.py"), "--list"],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = result.stdout.splitlines()
        self.assertEqual(listed, [describe(check) for check in CHECKS])
        for expected in ("python scripts/validate.py",
                         "python scripts/validate_plan.py examples/example-plan.json",
                         "python scripts/validate_plan.py examples/bounded-plan.json --json",
                         "python scripts/moves.py outcome examples/bounded-plan.json examples/bounded-outcome.json",
                         "python -m unittest discover -s tests -v",
                         "python evals/runner.py"):
            self.assertIn(expected, listed)
        self.assertTrue(listed[-1].startswith("python scripts/package.py --output "))

    def test_contributor_docs_and_ci_use_the_check_runner(self):
        for name in ("README.md", "CONTRIBUTING.md"):
            with self.subTest(file=name):
                self.assertIn("python scripts/check.py", (ROOT / name).read_text(encoding="utf-8"))
        workflow = ROOT / ".github/workflows/ci.yml"
        if workflow.is_file():
            self.assertIn("python scripts/check.py", workflow.read_text(encoding="utf-8"))


class VersionGateTests(unittest.TestCase):
    """The shim exists to refuse a v0.1 plan at the CLI boundary, not later."""

    def run_shim(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/moves_cli.py"), *args],
                              capture_output=True, text=True)

    def test_v02_only_commands_are_refused_before_moves_runs(self):
        from moves_cli import V02_REQUIRED_COMMANDS
        v01 = str(ROOT / "examples/example-plan.json")
        for command in sorted(V02_REQUIRED_COMMANDS):
            with self.subTest(command=command):
                result = self.run_shim(command, v01)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("requires a v0.2 plan", result.stderr)
                self.assertNotIn("experiment workflow requires", result.stderr)

    def test_docstring_lists_every_gated_command(self):
        import moves_cli
        listed = moves_cli.__doc__.split("Rules:")[0]
        for command in sorted(moves_cli.V02_REQUIRED_COMMANDS):
            with self.subTest(command=command):
                self.assertRegex(listed, r"(?<![\w-])" + command + r"(?![\w-])")
        self.assertIn("single source of\ntruth for behavior", listed)

    def test_shared_commands_still_accept_a_v01_plan(self):
        from moves_cli import SHARED_COMMANDS
        v01 = str(ROOT / "examples/example-plan.json")
        for command, extra in (("render", ()), ("review", ()), ("sources", ("--as-of", "2026-09-21", "--max-age-days", "30"))):
            with self.subTest(command=command):
                self.assertIn(command, SHARED_COMMANDS)
                self.assertEqual(self.run_shim(command, v01, *extra).returncode, 0)

    def test_unsupported_version_is_refused_for_a_gated_command(self):
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "plan.json"
            plan.write_text(json.dumps({**example(), "contract_version": "unconventional-moves/v9.9"}))
            result = self.run_shim("render", str(plan))
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("unsupported contract_version", result.stderr)

    def test_flags_before_the_plan_still_hit_the_version_gate(self):
        v01 = str(ROOT / "examples/example-plan.json")
        cases = (
            ("card", "--format", "json", v01),
            ("card", "--format=json", v01),
            ("screen", "--max-minutes", "20", "--exposure", "self_only", v01),
            ("render", "--format", "html", v01),
        )
        for args in cases:
            with self.subTest(args=args):
                result = self.run_shim(*args)
                if args[0] == "render":
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("requires a v0.2 plan", result.stderr)
                    self.assertNotIn("experiment workflow requires", result.stderr)

    def test_gate_uses_the_bounded_parser_and_does_not_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "plan.json"
            plan.write_text("[" * 10000 + "]" * 10000, encoding="utf-8")
            result = self.run_shim("render", str(plan))
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("FAIL", result.stderr)
            plan.write_text('{"contract_version": "unconventional-moves/v0.1", "goal": NaN}\n', encoding="utf-8")
            result = self.run_shim("render", str(plan))
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("non-standard JSON constant", result.stderr)
