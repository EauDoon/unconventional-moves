# Resume review from an exported handoff

Use Python 3.11 or 3.12 from the repository or an extracted package. All commands
are offline; none executes an experiment. A handoff has enough source data to
restore an editable plan and its supplied observations without copying fields
by hand. Copying only the latest observation can hide earlier stops.

```sh
python scripts/moves.py unpack-handoff handoff.json --output-dir restored
```

The command recomputes the bundle's digests and derived reviews before creating
any output. It accepts the existing handoff-v0.1 and handoff-v0.2 formats, which
both contain a v0.2 experiment plan. The handoff version is distinct from the
plan version. The v0.1 plan review/render workflow is unchanged.

The destination must be new and its parent must exist. Even an existing empty
directory or a destination symlink is refused. No filenames come from authored
plan content. All restored JSON files obey the normal 1 MB input bound.

| File | Meaning |
| --- | --- |
| `plan.json` | Exact parsed plan, including its original selection and revision binding |
| `checkpoints.json` | Every supplied raw observation, in order, with original notes and declarations |
| `handoff.json` | Verified source bundle, retained for later consistency checks |
| `resume-review.json` | Recomputed full timeline, checkpoint count, persistent stops, and pending human review |
| `README.md` | Instructions for reviewing records, recording cumulative observations, and separating revisions |

JSON formatting may change, but parsed numbers and strings are preserved,
including numeric representations that affect the digest. Missing measurements
remain `null`; measured zero stays zero. No observation is rebound to a different
plan. The command prints the resume review and exits 0 when restoration succeeds,
including when the decision is `stop_and_review`.

A legacy single-observation handoff restores a one-entry array. A plan-only
handoff restores `[]` and the decision `human_review_required`, with no invented
timeline or measurement. An empty supplied history does not establish that no
earlier activity occurred. An input or validation failure creates no directory.
An ordinary write failure attempts to clean up only the files this invocation
created. A process termination or cleanup failure can leave an incomplete
directory; use a fresh destination and rerun from the original handoff.

## Review before adding records

Read `restored/resume-review.json`. For a nonempty history:

```sh
python scripts/moves.py verify-handoff restored/handoff.json
python scripts/moves.py timeline restored/plan.json restored/checkpoints.json
python scripts/moves.py limits restored/plan.json restored/checkpoints.json
python scripts/moves.py debrief restored/plan.json restored/checkpoints.json --output debrief.md
python scripts/moves.py timeline restored/plan.json restored/checkpoints.json --format csv --output checkpoints.csv
python scripts/moves.py render restored/plan.json --format html --output review.html
```

Stops from any supplied checkpoint persist, even when later records clear a
flag, declare consent, or meet the numeric target. Records after a stop remain
marked for review. JSON is the source record; existing HTML escaping and CSV
formula protection still apply to review exports.

If another observation has actually been reported, prepare a draft:

```sh
python scripts/moves.py observation-draft restored/plan.json --output next-observation.json
```

Fill it with actual cumulative elapsed hours and active minutes, honest notes,
the actual consent/stop declarations, and a measured value or `null`. The unfilled
draft deliberately fails validation. Do not reset cumulative times or copy only
the latest row. After filling it, record into a new history file:

```sh
python scripts/moves.py record restored/plan.json next-observation.json --history restored/checkpoints.json --output next-checkpoints.json
python scripts/moves.py handoff restored/plan.json --timeline next-checkpoints.json --output next-handoff.json
```

The same `record --history` command accepts an empty restored history. `timeline`,
`limits`, `debrief`, and `handoff --timeline` require at least one observation.
Keep a plan-only handoff plan-only until there are actual records to include.
Recording after a stop describes supplied data; it never permits more activity.

## Keep revisions separate

```sh
python scripts/moves.py select restored/plan.json --move-id move-02 --reason "Review a different mechanism" --first-step "Review the alternative before any trial" --output revised.json
python scripts/moves.py compare restored/plan.json revised.json --output revision-review.json
python scripts/moves.py card revised.json --output revised-card.json
python scripts/moves.py observation-draft revised.json --output revised-observation.json
```

Replace the move ID, reason, and first step with your reviewed choice. Old
checkpoints must stay with the original plan. Reviewing the old history against
`revised.json` fails the revision binding; do not edit hashes to bypass that
check. A new selection or revision grants no approval or permission to restart.

## Run the synthetic walkthrough

With a new destination, from the repository or extracted package root:

```sh
python examples/replay-handoff.py --output replay
```

The script authors a fixture selection, binds three fictional observations,
exports and verifies a handoff, restores it, and produces HTML, CSV, and a
debrief. The first checkpoint has an unavailable measurement and a declared
stop; the second measures zero; the third meets the target. Recovery still
reports `stop_and_review` at checkpoint 1. A fourth supplied synthetic record
retains the stop. A new plan selection demonstrates rejection of the old
history and gets a fresh unfilled observation draft. The script exits nonzero
if these checks fail; an incomplete run has no `replay-summary.json`.

Inspect `replay/replay-summary.json`, `replay/restored/resume-review.json`,
`replay/checkpoints.csv`, `replay/review.html`, `replay/debrief.md`, and
`replay/revision-review.json`. Every observation is synthetic. No experiment
occurs, and these checks establish record handling, not real-world usefulness.

Restoration establishes internal consistency only. Unsigned bundles cannot
prove authorship, completeness, factual accuracy, consent, or approval. A
fully rewritten consistent bundle or omitted history cannot be detected here.
Verify provenance and completeness with the person supplying the records.
