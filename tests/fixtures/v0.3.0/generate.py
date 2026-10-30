#!/usr/bin/env python3
"""Regenerate the 0.3.0 handoff corpus with the 0.3.0 release code.

Run this only against an export of tag v0.3.0, never against later code. The
corpus exists to prove that later releases still accept what 0.3.0 wrote, so
files produced by any other version would make that proof meaningless.

    git archive v0.3.0 | tar -x -C EXPORT
    python tests/fixtures/v0.3.0/generate.py --release-root EXPORT --output NEW_DIRECTORY

Every record is synthetic language-practice data. No experiment occurred.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

NOTE = "Synthetic 0.3.0 corpus record; no experiment occurred."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release-root", type=Path, required=True, help="an export of tag v0.3.0")
    parser.add_argument("--output", type=Path, required=True, help="a new directory for the corpus")
    args = parser.parse_args()
    root = args.release_root.resolve()
    if (root / "VERSION").read_text(encoding="utf-8").strip() != "0.3.0":
        print("FAIL --release-root must be an export of tag v0.3.0", file=sys.stderr)
        return 1
    output = args.output
    output.mkdir()

    def run(*command):
        subprocess.run([sys.executable, str(root / "scripts/moves.py"), *map(str, command)],
                       check=True, capture_output=True)

    def read(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write(path: Path, value) -> None:
        path.write_bytes((json.dumps(value, indent=2) + "\n").encode("utf-8"))

    bounded = read(root / "examples/bounded-plan.json")
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        # A plan-only handoff-v0.1.
        run("handoff", root / "examples/bounded-plan.json", "--output", output / "plan-only.handoff.json")

        # A handoff-v0.1 whose observed 0.1 + 0.2 gives a 34-digit progress string.
        plan = copy.deepcopy(bounded)
        plan["moves"][0]["experiment"].update(baseline=0, target=7)
        write(work / "progress-plan.json", plan)
        run("observation-draft", work / "progress-plan.json", "--output", work / "progress-draft.json")
        observation = {**read(work / "progress-draft.json"), "observed_value": 0.1 + 0.2,
                       "elapsed_hours": 24, "active_minutes": 10, "notes": NOTE}
        write(work / "progress-observation.json", observation)
        run("handoff", work / "progress-plan.json", "--observation", work / "progress-observation.json",
            "--output", output / "observation.handoff.json")

        # The handoff-v0.2 that the synthetic replay writes.
        subprocess.run([sys.executable, str(root / "examples/replay-handoff.py"), "--output", str(work / "replay")],
                       check=True, capture_output=True)
        (output / "replay.handoff.json").write_bytes((work / "replay/handoff.json").read_bytes())

        # A handoff-v0.2 timeline covering the widened precision of 0.3.0: a
        # baseline of 1e30 with an observed 2e-5, elapsed hours 0.2 then 0.3,
        # and consenting participants without confirmed consent.
        plan = copy.deepcopy(bounded)
        plan["moves"][0]["experiment"].update(baseline=1e30, target=2e30, exposure="consenting_participants")
        write(output / "record-plan.json", plan)
        run("observation-draft", output / "record-plan.json", "--output", work / "precision-draft.json")
        draft = read(work / "precision-draft.json")
        for index, (hours, minutes) in enumerate(((0.2, 6), (0.3, 12)), 1):
            write(work / f"precision-{index}.json", {**draft, "observed_value": 2e-5, "elapsed_hours": hours,
                                                     "active_minutes": minutes, "notes": NOTE})
        run("record", output / "record-plan.json", work / "precision-1.json", "--output", work / "checkpoints-1.json")
        run("record", output / "record-plan.json", work / "precision-2.json", "--history", work / "checkpoints-1.json",
            "--output", output / "record-checkpoints.json")
        run("handoff", output / "record-plan.json", "--timeline", output / "record-checkpoints.json",
            "--output", output / "precision.handoff.json")

    names = sorted(path.name for path in output.iterdir())
    (output / "SHA256SUMS").write_bytes("".join(
        hashlib.sha256((output / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in names).encode("ascii"))
    for name in names:
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
