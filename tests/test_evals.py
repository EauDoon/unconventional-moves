"""Fixture integrity only. These checks do not measure model behavior."""

import importlib.util
import io
import json
import hashlib
import re
import shutil
import tempfile
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate fixture key")
        result[key] = value
    return result


def paired_dimension_changes(scored: list[dict]) -> dict:
    """Recount better, same, and worse per rubric dimension from the records.

    Only primary pairs count, and a pair where either side is N/A is excluded
    rather than scored, matching the recorded limitation that N/A dimensions
    are not passing scores.
    """
    changes: dict = {}
    for row in scored:
        if row["repeat"]:
            continue
        baseline = row["candidates"]["baseline"]["scores"]
        for dimension, cell in row["candidates"]["revised"]["scores"].items():
            before, after = baseline[dimension]["score"], cell["score"]
            if before is None or after is None:
                continue
            bucket = changes.setdefault(dimension, Counter())
            bucket["better" if after > before else "worse" if after < before else "same"] += 1
    return {dimension: {outcome: counts[outcome] for outcome in ("better", "same", "worse")}
            for dimension, counts in changes.items()}


def rubric_dimensions(rubric_text: str) -> set:
    """Dimension keys documented by the frozen rubric table.

    Recorded keys drop a joining "and", so "Downside and third parties" scores
    as downside_third_parties. A new rubric row that does not follow that rule
    fails here instead of being scored under an unrecognised key.
    """
    table = rubric_text.split("## Gates and judgments")[0]
    keys = set()
    for line in table.splitlines():
        if not line.startswith("|"):
            continue
        name = line.split("|")[1].strip()
        if not name or set(name) <= {"-", ":", " "}:
            continue
        keys.add(re.sub(r"[^a-z0-9]+", "_", name.lower().replace(" and ", " ")).strip("_"))
    keys.discard("dimension")
    return keys


# The longest phrase the tuning surface legitimately shares with a held-out
# prompt is the six-word invocation boilerplate, so a longer verbatim run is a
# quote rather than shared vocabulary.
HELD_OUT_NGRAM = 7
TUNING_SURFACE_DIRS = ("skill", "docs", "templates", "examples")
TUNING_SURFACE_FILES = ("README.md", "CONTRIBUTING.md", "CHANGELOG.md", "PROVENANCE.md", "SECURITY.md")


def _ngrams(tokens: list[str], size: int) -> set:
    return {tuple(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


def held_out_prompt_leaks() -> list[str]:
    """Report tuning files that quote a held-out prompt.

    CONTRIBUTING requires held-out cases to stay separate from tuning and
    evals/README.md repeats it. Reservation metadata was checked; the text of a
    held-out prompt appearing in the skill or its guidance was not.
    """
    surface = {}
    for relative in TUNING_SURFACE_DIRS:
        surface.update({path: path.read_text(encoding="utf-8")
                        for path in (ROOT / relative).rglob("*")
                        if path.is_file() and path.suffix in (".md", ".yaml")})
    surface.update({ROOT / name: (ROOT / name).read_text(encoding="utf-8")
                    for name in TUNING_SURFACE_FILES if (ROOT / name).is_file()})
    surface_grams = {path: _ngrams(re.findall(r"[a-z0-9]+", text.lower()), HELD_OUT_NGRAM)
                     for path, text in surface.items()}
    suite = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))
    leaks = []
    for case in suite["cases"]:
        if case["split"] != "held_out":
            continue
        quoted = _ngrams(re.findall(r"[a-z0-9]+", case["prompt"].lower()), HELD_OUT_NGRAM)
        for path, grams in surface_grams.items():
            overlap = sorted(" ".join(gram) for gram in quoted & grams)
            if overlap:
                leaks.append(f"{case['id']} quoted in {path.relative_to(ROOT).as_posix()}: {overlap[0]}")
    return sorted(leaks)


class EvaluationFixtureTests(unittest.TestCase):
    def test_recorded_probe_integrity_not_semantic_quality(self):
        records = [json.loads(line) for line in (ROOT / "evals/session-probe.jsonl").read_text(encoding="utf-8").splitlines()]
        responses = [row for row in records if row["record_type"] == "response"]
        cases = {case["id"]: case for case in self.suite["cases"]}
        expected = {(condition, case, repeat) for condition in ("baseline", "revised") for case in cases
                    for repeat in ([False, True] if case in {"cosmetic-distribution", "heldout-learning-bottleneck"} else [False])}
        self.assertEqual(len(responses), len(expected))
        self.assertEqual({(row["condition"], row["case_id"], row["repeat"]) for row in responses}, expected)
        for row in responses:
            self.assertEqual(row["prompt"], cases[row["case_id"]]["prompt"])
            self.assertEqual(hashlib.sha256(row["response"].encode("utf-8")).hexdigest(), row["response_sha256"])
        for row in records:
            if row["record_type"] == "instructions":
                for filename, entry in row["files"].items():
                    self.assertEqual(hashlib.sha256(entry["text"].encode("utf-8")).hexdigest(), entry["sha256"])
                    if row["condition"] == "revised":
                        current = (ROOT / "skill/unconventional-moves" / filename).read_text(encoding="utf-8")
                        self.assertEqual(current, entry["text"].replace("\r\n", "\n"))
        results = json.loads((ROOT / "evals/results.json").read_text(encoding="utf-8"))
        scored = results["records"]
        self.assertEqual(len(scored), 22)
        self.assertEqual({(row["case_id"], row["repeat"]) for row in scored},
                         {(case, repeat) for _, case, repeat in expected})
        for row in scored:
            self.assertEqual(set(row["candidates"]), {"baseline", "revised"})
            for candidate in row["candidates"].values():
                self.assertEqual(set(candidate["scores"]), self.rubric_dimensions)
                for dimension in candidate["scores"].values():
                    self.assertIn(dimension["score"], (None, 0, 1, 2))
                    self.assertTrue(dimension["evidence"].strip())
        self.assertEqual(dict(Counter(row["preference"] for row in scored if not row["repeat"])),
                         results["preferences"]["primary"])
        # Every declared tally must be recomputable from the records, using the
        # declared split rather than a field the result file asserts about itself.
        held_out = {case for case, declared in cases.items() if declared["split"] == "held_out"}
        self.assertEqual(dict(Counter(row["preference"] for row in scored
                                      if not row["repeat"] and row["case_id"] in held_out)),
                         results["preferences"]["held_out"])
        self.assertEqual(dict(Counter(row["preference"] for row in scored if row["repeat"])),
                         results["preferences"]["repeats"])
        self.assertEqual(paired_dimension_changes(scored), results["paired_dimension_changes"])

    @classmethod
    def setUpClass(cls):
        cls.suite = json.loads(
            (ROOT / "evals" / "cases.json").read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
        )
        cls.rubric_dimensions = rubric_dimensions(
            (ROOT / "evals" / "rubric.md").read_text(encoding="utf-8"))

    def test_fixture_shape_and_unique_prompts(self):
        self.assertEqual(self.suite["suite_version"], "unconventional-moves-behavior/v1")
        self.assertIs(self.suite["synthetic"], True)
        cases = self.suite["cases"]
        self.assertEqual(len(cases), 20)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertEqual(len({case["prompt"] for case in cases}), len(cases))
        required = {"id", "split", "domain", "tags", "expected", "prompt", "review_notes"}
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertLessEqual(required, set(case))
                self.assertLessEqual(set(case), required | {"json_contract"})
                self.assertRegex(case["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                for field in required - {"tags"}:
                    self.assertIsInstance(case[field], str)
                    self.assertTrue(case[field].strip())
                self.assertIsInstance(case["tags"], list)
                self.assertTrue(case["tags"])
                self.assertEqual(len(case["tags"]), len(set(case["tags"])))
                self.assertIn(case["split"], {"development", "held_out"})
                self.assertIn(case["expected"], {
                    "apply", "do_not_apply", "clarify_or_apply", "clarify_or_limit",
                    "limit", "apply_v01_or_clarify", "refuse_or_redirect",
                })

    def test_declared_coverage_and_reserved_split(self):
        cases = self.suite["cases"]
        tags = {tag for case in cases for tag in case["tags"]}
        self.assertLessEqual({
            "explicit_invocation", "implicit_invocation", "negative_trigger",
            "vague_brief", "tight_budget", "conflicting_constraints",
            "near_duplicates", "unavailable_sources", "missing_numeric_baselines",
            "prompt_injection", "unsafe_objective", "json_v01", "json_v02",
        }, tags)
        domains = {
            "partnership_activation", "product_adoption", "distribution",
            "operational_efficiency", "personal_learning",
        }
        self.assertEqual({case["domain"] for case in cases}, domains)
        held_out = [case for case in cases if case["split"] == "held_out"]
        self.assertEqual(len(held_out), 5)
        self.assertEqual({case["domain"] for case in held_out}, domains)
        # This checks reservation metadata, not whether a human avoided leakage.
        self.assertTrue(all(case["id"].startswith("heldout-") for case in held_out))

    def test_requested_contracts_exist_and_are_bundled(self):
        versions = {
            "unconventional-moves/v0.1": "moves.schema.json",
            "unconventional-moves/v0.2": "moves-v0.2.schema.json",
        }
        requested = {case["json_contract"] for case in self.suite["cases"] if "json_contract" in case}
        self.assertEqual(requested, set(versions))
        for version, filename in versions.items():
            canonical = ROOT / "schemas" / filename
            bundled = ROOT / "skill" / "unconventional-moves" / "references" / filename
            self.assertEqual(canonical.read_bytes(), bundled.read_bytes())
            schema = json.loads(canonical.read_text(encoding="utf-8"))
            self.assertEqual(schema["properties"]["contract_version"]["const"], version)

    def test_tuning_surface_does_not_quote_a_held_out_prompt(self):
        self.assertEqual(held_out_prompt_leaks(), [])

    def test_runner_rejects_duplicate_fixture_keys(self):
        spec = importlib.util.spec_from_file_location("eval_runner_keys", ROOT / "evals" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            runner.load_fixture_json('{"expected": "refuse_or_redirect", "expected": "apply"}')
        with tempfile.TemporaryDirectory() as td:
            cases = Path(td) / "cases"
            shutil.copytree(ROOT / "evals" / "cases", cases)
            target = next(cases.glob("*.json"))
            text = target.read_text(encoding="utf-8").lstrip()
            target.write_text('{\n  "id": "tampered",\n' + text[1:], encoding="utf-8")
            runner.CASES_DIR = cases
            stderr = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                code = runner.main()
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_runner_rejects_non_object_fixtures(self):
        spec = importlib.util.spec_from_file_location("eval_runner_shape", ROOT / "evals" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        for payload in ("[]\n", "null\n"):
            with self.subTest(payload=payload.strip()):
                with tempfile.TemporaryDirectory() as td:
                    cases = Path(td) / "cases"
                    shutil.copytree(ROOT / "evals" / "cases", cases)
                    target = next(cases.glob("*.json"))
                    target.write_text(payload, encoding="utf-8")
                    runner.CASES_DIR = cases
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = runner.main()
                self.assertEqual(code, 1)
                self.assertIn(target.stem, stdout.getvalue())
                self.assertIn("JSON object", stdout.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue() + stdout.getvalue())

    def test_runner_rejects_nonfinite_fixture_numbers(self):
        spec = importlib.util.spec_from_file_location("eval_runner_numbers", ROOT / "evals" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        for raw in ('{"score": NaN}', '{"score": Infinity}', '{"score": -Infinity}', '{"score": 1e400}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    runner.load_fixture_json(raw)
        with tempfile.TemporaryDirectory() as td:
            cases = Path(td) / "cases"
            shutil.copytree(ROOT / "evals" / "cases", cases)
            target = next(cases.glob("*.json"))
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace("{", '{"leak": NaN, ', 1), encoding="utf-8")
            runner.CASES_DIR = cases
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = runner.main()
        self.assertEqual(code, 1)
        self.assertIn(target.stem, stdout.getvalue())
        self.assertIn("non-standard JSON constant", stdout.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue() + stdout.getvalue())

    def test_suite_shape_errors_use_exit_code_2(self):
        spec = importlib.util.spec_from_file_location("eval_runner_exit", ROOT / "evals" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as td:
            cases = Path(td) / "cases"
            shutil.copytree(ROOT / "evals" / "cases", cases)
            next(cases.glob("heldout-*.json")).unlink()
            runner.CASES_DIR = cases
            with redirect_stdout(io.StringIO()):
                code = runner.main()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
