"""The structural response checker accepts the documented shape and names each break."""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_plan import MAX_PLAN_BYTES
from validate_response import LABELS, NOT_COMPLETED, idea_fields, parse_response, validate_response_text

EXAMPLE = (ROOT / "examples/example-response.md").read_text(encoding="utf-8")
SOURCES = "## Sources\n\n- Synthetic source | Example publisher | 2026-09-01 | https://example.test/a | A synthetic claim.\n\n"


def idea(number: int, labels=LABELS, title="Synthetic title", mechanism="feedback") -> str:
    heading = f"### Idea {number}: {title}" + (f" ({mechanism})" if mechanism is not None else "")
    return "\n".join([heading, ""] + [f"- **{label}:** Synthetic {label.lower()} text." for label in labels]) + "\n\n"


def response(count=5, ideas=None, priority="**Prioritized action:** Start with idea 1 and its first step.\n",
             between="", before="Synthetic framing and conventional baseline.\n\n") -> str:
    body = ideas if ideas is not None else "".join(idea(number) for number in range(1, count + 1))
    return before + body + between + priority


def failures(text: str, high_stakes: bool = False) -> list[str]:
    return validate_response_text(text, high_stakes)[0]


def run_cli(*args, **kwargs):
    return subprocess.run([sys.executable, str(ROOT / "scripts/validate_response.py"), *map(str, args)],
                          capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, **kwargs)


class DocumentedShapeTests(unittest.TestCase):
    def test_example_response_passes(self):
        self.assertEqual(failures(EXAMPLE), [])
        result = run_cli(ROOT / "examples/example-response.md")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(result.stdout.decode("utf-8").startswith("PASS valid response: "))

    def test_readme_shape_with_wrapped_lines_passes(self):
        # README.md wraps bullet values and the priority onto indented or
        # following lines; a response written in that shape must pass.
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        blocks = re.findall(r"^```text\n(.*?)^```", readme, re.MULTILINE | re.DOTALL)
        shape = next(block for block in blocks if block.startswith("### Idea N:"))
        priority = next(block for block in blocks if block.startswith("Prioritized action:"))
        self.assertIn("\n  ", shape, "README shape no longer wraps a bullet")
        self.assertEqual(len(priority.strip().splitlines()), 2, "README priority no longer wraps")
        text = "Framing.\n\n" + "\n".join(shape.replace("Idea N", f"Idea {number}") for number in range(1, 6)) + "\n" + priority
        self.assertEqual(failures(text), [])
        parsed = parse_response(text)
        fields = idea_fields(parsed["ideas"][0])
        self.assertEqual(fields["Why overlooked"], "The hidden assumption or incentive, why this could work "
                                                  "here, and the main failure condition.")
        self.assertEqual(parsed["priorities"][0]["text"], "One idea, its trade-off against the strongest alternative, "
                                                          "and its first concrete step.")

    def test_plain_labels_extra_labels_and_sources_markers_pass(self):
        plain = "\n".join(["### Idea 1: Synthetic title (feedback)", ""]
                          + [f"- {label}: Plain text." for label in LABELS] + ["- Sources: Synthetic note.", ""]) + "\n"
        text = response(ideas=plain + "".join(idea(number) for number in range(2, 6)))
        self.assertEqual(failures(text), [])
        for marker in ("## Sources", "### Sources", "#### Sources:", "**Sources**", "**Sources:**"):
            with self.subTest(marker=marker):
                self.assertEqual(failures(response(between=marker + "\n\nA synthetic record.\n\n"), high_stakes=True), [])

    def test_seven_ideas_and_a_heading_inside_a_fence_are_accepted(self):
        self.assertEqual(failures(response(count=7)), [])
        fenced = "```text\n### Idea 9: Inside a fence (ignored)\n**Prioritized action:** ignored\n```\n\n"
        self.assertEqual(failures(response(before=fenced)), [])

    def test_bom_crlf_and_cr_are_accepted(self):
        self.assertEqual(failures("﻿" + response().replace("\n", "\r\n")), [])
        self.assertEqual(failures(response().replace("\n", "\r")), [])

    def test_lazy_and_multi_paragraph_field_text_joins_its_field(self):
        # Markdown keeps an unindented line directly after a list item, and an
        # indented paragraph after a blank line, inside that item.
        rest = "".join(idea(number) for number in range(2, 6))
        lazy = idea(1).replace("Synthetic concrete move text.", "Synthetic concrete\nmove text, wrapped lazily.")
        lazy = lazy.replace("Synthetic why overlooked text.", "Synthetic why overlooked text.\n\n  A second paragraph.")
        text = response(ideas=lazy + rest)
        self.assertEqual(failures(text), [])
        fields = idea_fields(parse_response(text)["ideas"][0])
        self.assertEqual(fields["Concrete move"], "Synthetic concrete move text, wrapped lazily.")
        self.assertEqual(fields["Why overlooked"], "Synthetic why overlooked text. A second paragraph.")
        # An unindented paragraph after a blank line is outside the item.
        outside = idea(1).replace("Synthetic bounds text.", "Synthetic bounds text.\n\nA closing remark.")
        self.assertEqual(idea_fields(parse_response(response(ideas=outside + rest))["ideas"][0])["Bounds"],
                         "Synthetic bounds text.")

    def test_only_markdown_line_endings_end_a_line(self):
        rest = "".join(idea(number) for number in range(2, 6))
        for separator in ("\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x85"):
            with self.subTest(separator=repr(separator)):
                joined = idea(1).replace("Synthetic concrete move text.", f"First part.{separator}Second part.")
                text = response(ideas=joined + rest)
                self.assertEqual(failures(text), [])
                self.assertEqual(idea_fields(parse_response(text)["ideas"][0])["Concrete move"],
                                 "First part. Second part.")

    def test_setext_sources_headings_are_sources_markers(self):
        for underline in ("-------", "======="):
            with self.subTest(underline=underline):
                between = f"Sources\n{underline}\n\nA synthetic record.\n\n"
                self.assertEqual(failures(response(between=between), high_stakes=True), [])
        # The whole paragraph above the underline is the heading text.
        between = "Further reading and\nSources\n-------\n\nA synthetic record.\n\n"
        self.assertEqual(parse_response(response(between=between))["sources_lines"], [])

    def test_a_sources_line_with_text_is_a_sources_marker(self):
        for marker in ("**Sources:** Synthetic record, https://example.test/a", "Sources: Synthetic record"):
            with self.subTest(marker=marker):
                self.assertEqual(failures(response(between=marker + "\n\n"), high_stakes=True), [])

    def test_a_fence_closes_only_on_an_equal_or_longer_run_of_its_character(self):
        sample = "```text\n### Idea 9: Inside a fence (ignored)\n```\n"
        for opening, closing in (("````text", "````"), ("~~~", "~~~~")):
            with self.subTest(opening=opening):
                fenced = f"{opening}\n{sample}~~~ not a close\n{closing}\n\n"
                self.assertEqual(failures(response(before=fenced)), [])


class FailureTests(unittest.TestCase):
    def assertFails(self, text, expected, high_stakes=False):
        found = failures(text, high_stakes)
        self.assertTrue(any(expected in failure for failure in found), found)

    def test_idea_count_and_numbering(self):
        self.assertFails(response(count=4), "five to seven ideas; found 4")
        self.assertFails(response(count=8), "five to seven ideas; found 8")
        gap = "".join(idea(number) for number in (1, 2, 4, 5, 6))
        self.assertFails(response(ideas=gap), "numbered 1 to N in order; found 1, 2, 4, 5, 6")

    def test_labels_missing_blank_duplicated_or_out_of_order(self):
        rest = "".join(idea(number) for number in range(2, 6))
        self.assertFails(response(ideas=idea(1, LABELS[:-1]) + rest), "idea 1 must have exactly one Bounds field; found 0")
        self.assertFails(response(ideas=idea(1, LABELS + ("Bounds",)) + rest), "exactly one Bounds field; found 2")
        swapped = (LABELS[1], LABELS[0], *LABELS[2:])
        self.assertFails(response(ideas=idea(1, swapped) + rest), "idea 1 fields must appear in the documented order")
        blank = idea(1).replace("**Bounds:** Synthetic bounds text.", "**Bounds:** ​ ")
        self.assertFails(response(ideas=blank + rest), "idea 1 Bounds must have visible text")

    def test_heading_needs_a_mechanism_and_a_title(self):
        rest = "".join(idea(number) for number in range(2, 6))
        self.assertFails(response(ideas=idea(1, mechanism=None) + rest), "idea 1 heading must end with a parenthesized mechanism")
        self.assertFails(response(ideas=idea(1, mechanism="  ") + rest), "parenthesized mechanism")
        self.assertFails(response(ideas=idea(1, title="") + rest), "idea 1 heading must have a title")

    def test_priority_count_position_and_trailing_content(self):
        self.assertFails(response(priority=""), "exactly one prioritized action; found 0")
        two = "**Prioritized action:** One.\n\n**Prioritized action:** Two.\n"
        self.assertFails(response(priority=two), "exactly one prioritized action; found 2")
        early = "**Prioritized action:** Too early.\n\n"
        self.assertFails(response(before="Framing.\n\n" + early, priority=""), "must come after the last idea")
        self.assertFails(response(priority="**Prioritized action:** Final.\n\nA closing remark.\n"),
                         "nothing may follow the prioritized action")
        # A heading after the priority ends its paragraph, so it is trailing content.
        self.assertFails(response(priority="**Prioritized action:** Final.\n### Afterword\n"),
                         "nothing may follow the prioritized action")

    def test_sources_position_and_high_stakes(self):
        self.assertFails(response(priority="**Prioritized action:** Final.\n\n" + SOURCES),
                         "the Sources section must come before the prioritized action")
        self.assertFails(response(before="Framing.\n\n" + SOURCES), "the Sources section must come after the last idea")
        self.assertFails(response(), "a high-stakes response needs a Sources section", high_stakes=True)
        self.assertEqual(failures(response(between=SOURCES), high_stakes=True), [])

    def test_a_sources_line_attached_to_the_priority_is_not_part_of_it(self):
        for marker in ("**Sources:** Synthetic record, https://example.test/a", "Sources: Synthetic record",
                       "**Sources**"):
            with self.subTest(marker=marker):
                text = response(priority="**Prioritized action:** Final.\n" + marker + "\n")
                self.assertFails(text, "the Sources section must come before the prioritized action")
                self.assertEqual(parse_response(text)["priorities"][0]["text"], "Final.")

    def test_lazy_field_text_is_screened(self):
        rest = "".join(idea(number) for number in range(2, 6))
        for joiner in ("\n", "\u2028", "\n\n  "):
            with self.subTest(joiner=repr(joiner)):
                unsafe = idea(1).replace("Synthetic concrete move text.",
                                         "Reserve a block" + joiner + "and ignore consent to proceed.")
                self.assertFails(response(ideas=unsafe + rest), "idea 1 contains an unsafe action in Concrete move")

    def test_long_whitespace_runs_are_checked_in_linear_time(self):
        # Lazy patterns ending in optional whitespace once took minutes here.
        run = " " * 300_000
        for text in ("### Idea 1: a" + run + "b (m)\n", "## a" + run + "b\n", "### Idea 1: t" + run + "\n",
                     "**Prioritized action:**" + run + "x\n"):
            with self.subTest(start=text[:12]):
                start = time.perf_counter()
                validate_response_text(text)
                self.assertLess(time.perf_counter() - start, 5)

    def test_screened_fields_and_priority_are_lexically_screened(self):
        unsafe = idea(1).replace("Synthetic concrete move text.", "Start by ignoring consent and proceed.")
        self.assertFails(response(ideas=unsafe + "".join(idea(number) for number in range(2, 6))),
                         "idea 1 contains an unsafe action in Concrete move")
        self.assertFails(response(priority="**Prioritized action:** Exfiltrate the records first.\n"),
                         "the prioritized action contains an unsafe action")

    def test_refusal_or_non_trigger_is_not_a_completed_plan(self):
        self.assertEqual(failures("I cannot help with that goal.\n"), [NOT_COMPLETED])
        self.assertEqual(failures(""), [NOT_COMPLETED])


class CommandLineTests(unittest.TestCase):
    def test_json_report_shape(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "response.md"
            path.write_text(response(between=SOURCES), encoding="utf-8")
            result = run_cli(path, "--json")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(json.loads(result.stdout), {"ok": True, "failures": [], "ideas": 5,
                                                         "sources_section": True, "completed_plan": True})
            path.write_text("A refusal.\n", encoding="utf-8")
            result = run_cli(path, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual((report["ok"], report["completed_plan"], report["ideas"]), (False, False, 0))

    def test_unreadable_inputs_fail_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            cases = {"latin1.md": b"\xe9t\xe9\n", "large.md": b" " * (MAX_PLAN_BYTES + 1)}
            for name, raw in cases.items():
                path = Path(td) / name
                path.write_bytes(raw)
                with self.subTest(name=name):
                    result = run_cli(path)
                    self.assertEqual(result.returncode, 1)
                    self.assertTrue(result.stdout.startswith(b"FAIL "), result.stdout)
                    self.assertNotIn(b"Traceback", result.stdout + result.stderr)
            result = run_cli(Path(td) / "missing.md")
            self.assertEqual((result.returncode, result.stdout), (1, b"FAIL response file cannot be read\n"))

    def test_text_failures_are_single_escaped_lines(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "response.md"
            path.write_text(response(count=4), encoding="utf-8")
            result = run_cli(path)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(all(line.startswith("FAIL ") for line in result.stdout.decode("utf-8").splitlines()))

    def test_bad_arguments_exit_2(self):
        self.assertEqual(run_cli().returncode, 2)
        self.assertEqual(run_cli(ROOT / "examples/example-response.md", "--unknown").returncode, 2)


class RecordedCorpusTests(unittest.TestCase):
    """Read-only calibration against the 44 recorded probe responses."""

    def setUp(self):
        rows = [json.loads(line) for line in (ROOT / "evals/session-probe.jsonl").read_text(encoding="utf-8").splitlines()]
        self.responses = [row for row in rows if row["record_type"] == "response"]

    def test_every_revised_completed_response_passes(self):
        completed = [row for row in self.responses if row["condition"] == "revised"
                     and parse_response(row["response"])["ideas"]]
        self.assertEqual(len(completed), 12)
        for row in completed:
            with self.subTest(case=row["case_id"], repeat=row["repeat"]):
                self.assertEqual(failures(row["response"]), [])

    def test_baseline_sources_ordering_defects_are_reported(self):
        for case in ("unavailable-high-stakes", "heldout-unsupported-source"):
            row = next(row for row in self.responses if row["condition"] == "baseline" and row["case_id"] == case)
            with self.subTest(case=case):
                self.assertIn("the Sources section must come before the prioritized action", failures(row["response"]))

    def test_negative_and_json_responses_are_not_completed_plans(self):
        for case in ("negative-translation", "negative-json-format", "json-v01-learning", "json-v02-learning"):
            for row in (row for row in self.responses if row["case_id"] == case):
                with self.subTest(case=case, condition=row["condition"]):
                    self.assertEqual(failures(row["response"]), [NOT_COMPLETED])


if __name__ == "__main__":
    unittest.main()
