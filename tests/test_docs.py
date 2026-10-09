"""Execute the documented offline commands so the docs cannot drift silently.

Each document runs in its own fresh copy of scripts/ and examples/, with
`python` mapped to the running interpreter. A fenced json block in the docs
lists the synthetic values a reader enters into an observation file; it is
merged into that file before the next `record` command, as a reader would.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"^```([a-z]*)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def fenced_blocks(text: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(2)) for match in FENCE.finditer(text)]


def shell_commands(block: str) -> list[list[str]]:
    """Join backslash continuations and split each command like a POSIX shell."""
    commands, pending = [], ""
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        command = (pending + stripped).strip()
        pending = ""
        if command and not command.startswith("#"):
            commands.append(shlex.split(command))
    return commands


def section(text: str, heading: str) -> str:
    start = text.index(heading + "\n")
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end < 0 else text[start:end]


class DocumentedCommandTests(unittest.TestCase):
    def run_blocks(self, blocks: list[tuple[str, str]]) -> int:
        """Run every sh block in order in a fresh project copy; return the command count."""
        executed = 0
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            for name in ("scripts", "examples"):
                shutil.copytree(ROOT / name, work / name, ignore=shutil.ignore_patterns("__pycache__"))
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            entered = None
            for language, body in blocks:
                if language == "json":
                    entered = json.loads(body)
                    continue
                if language != "sh":
                    continue
                for command in shell_commands(body):
                    with self.subTest(command=" ".join(command)):
                        self.assertEqual(command[0], "python", "documented commands use python")
                        if command[1:3] == ["scripts/moves.py", "record"]:
                            self.assertIsNotNone(entered, "record needs the documented observation values")
                            observation = work / command[4]
                            data = json.loads(observation.read_text(encoding="utf-8"))
                            data.update(entered)
                            observation.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                            entered = None
                        result = subprocess.run([sys.executable, *command[1:]], cwd=work, env=env,
                                                capture_output=True, text=True, encoding="utf-8")
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        executed += 1
        return executed

    def test_usage_recipes_run_in_order(self):
        text = (ROOT / "docs/usage-recipes.md").read_text(encoding="utf-8")
        executed = self.run_blocks(fenced_blocks(text))
        self.assertGreaterEqual(executed, 15)

    def test_readme_offline_workflow_runs(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        blocks = [block for block in fenced_blocks(section(text, "## Optional offline workflow"))
                  if block[0] == "sh"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(self.run_blocks(blocks), 5)


if __name__ == "__main__":
    unittest.main()
