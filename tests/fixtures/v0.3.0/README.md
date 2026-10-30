# Handoff corpus written by release 0.3.0

These files were written by the 0.3.0 release code, tag `v0.3.0` at commit
`5fa93cefe65022497677389e67d21f1123b0a052`. `tests/test_compat.py` checks
that the current code still verifies and restores every one of them, so a
later change to a derived string cannot silently reject handoffs that users
exported with 0.3.0. All content is synthetic language-practice data; no
experiment occurred.

| File | What it covers |
| --- | --- |
| `plan-only.handoff.json` | A plan-only `handoff-v0.1` of `examples/bounded-plan.json` |
| `observation.handoff.json` | A `handoff-v0.1` whose observed 0.1 + 0.2 gives a 34-digit progress string |
| `replay.handoff.json` | The `handoff-v0.2` that `examples/replay-handoff.py` writes |
| `precision.handoff.json` | A `handoff-v0.2` with a baseline of 1e30 and an observed 2e-5, elapsed hours 0.2 then 0.3, and consenting participants without confirmed consent |
| `record-plan.json`, `record-checkpoints.json` | The plan and the cumulative history that `record` built for `precision.handoff.json` |
| `SHA256SUMS` | SHA-256 of each generated file |

They were generated with the 0.3.0 code, never with later code, and each
handoff was checked with the 0.3.0 `verify-handoff` before it was committed:

```sh
mkdir v030
git archive v0.3.0 | tar -x -C v030
python tests/fixtures/v0.3.0/generate.py --release-root v030 --output corpus
cd v030
python scripts/moves.py verify-handoff ../corpus/plan-only.handoff.json
python scripts/moves.py verify-handoff ../corpus/observation.handoff.json
python scripts/moves.py verify-handoff ../corpus/replay.handoff.json
python scripts/moves.py verify-handoff ../corpus/precision.handoff.json
```

Never edit or regenerate these files. When a release changes a derived
string, add that release's corpus in a new directory beside this one.
