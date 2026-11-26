"""Check user entry points, both plan versions, and the offline graph links."""
import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DeskTests(unittest.TestCase):
    def cli(self, *args, code=0):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/moves_cli.py"), *args],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def test_both_contracts(self):
        for path in ("examples/example-plan.json", "examples/bounded-plan.json"):
            plan = json.loads((ROOT / path).read_text(encoding="utf-8"))
            first, second = plan["moves"][:2]
            index = json.loads(self.cli("index", path))
            self.assertEqual([m["id"] for m in index["moves"]], [m["id"] for m in plan["moves"]])
            self.assertEqual(index["selected_move_id"], plan.get("selected_move_id"))
            self.assertEqual(json.loads(self.cli("inspect", path, "--move-id", first["id"])), first)
            contrast = json.loads(self.cli("contrast", path, "--first", first["id"], "--second", second["id"]))
            rows = {item["field"]: (item["first"], item["second"]) for item in contrast["fields"]}
            self.assertEqual(rows["stop_condition"], (first["stop_condition"], second["stop_condition"]))
            self.assertEqual("experiment.metric" in rows, "experiment" in first)
            self.assertEqual(contrast["plan_sha256"], index["plan_sha256"])
            review = json.loads(self.cli("review", path))
            worksheet = self.cli("review", path, "--format", "markdown")
            self.assertIn(index["plan_sha256"], worksheet)
            self.assertTrue(all("- [ ] " + prompt in worksheet for prompt in review["human_checks"]))

    def test_help_and_failed_lookups(self):
        plan = "examples/example-plan.json"
        self.assertIn("--format", self.cli("card", plan, "--help"))
        self.cli("card", plan, code=1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "output.json"
            self.cli("inspect", plan, "--move-id", "missing", "--output", path, code=1)
            self.cli("contrast", plan, "--first", "move-01", "--second", "move-01", "--output", path, code=1)
            self.assertFalse(path.exists())

    def test_offline_atlas_directory(self):
        atlas = ROOT / "docs/experiment-atlas.html"
        nodes, edges, links = set(), set(), []

        class Directory(HTMLParser):
            def handle_starttag(self, tag, attrs):
                fields = dict(attrs)
                if tag == "article":
                    nodes.add(fields["id"])
                    edges.update(filter(None, fields["data-outputs"].split(",")))
                if tag == "a" and fields.get("href"):
                    links.append(fields["href"])

        Directory().feed(atlas.read_text(encoding="utf-8"))
        self.assertEqual(len(nodes), 8)
        self.assertLessEqual(edges, nodes)
        for link in links:
            if link.startswith("#"):
                self.assertIn(link[1:], nodes)
            else:
                self.assertTrue((atlas.parent / link).is_file(), link)


if __name__ == "__main__":
    unittest.main()
