# Usage recipes

Seven copy-paste recipes that exercise the actual offline CLI. They use only
files and commands that ship in this repository: `examples/example-plan.json`
is a v0.1 plan, `examples/example-response.md` is the same plan written as a
prose skill response, `examples/bounded-plan.json` is a v0.2 bounded plan, and
`examples/bounded-outcome.json` is a synthetic outcome bound to its plan
revision. Every recipe calls `python scripts/moves.py <command>` directly,
with flags that exist in `scripts/moves.py`. `scripts/moves_cli.py` accepts
the same commands and adds an earlier refusal of a v0.1 plan for v0.2-only
commands. The recipes run in order from one working directory, and
`tests/test_docs.py` executes them. Replace the output filenames when an
artifact already exists. A successful
exit code only means a report was produced; it does not approve or start
anything.

## Recipe 1: Start from the synthetic v0.1 plan and render a Markdown report

`init --contract v0.1` copies `examples/example-plan.json` for editing.
Validate the copy, then render an inert Markdown report.

```sh
python scripts/moves.py init --contract v0.1 --output v01-draft.json
python scripts/validate_plan.py v01-draft.json
python scripts/moves.py render v01-draft.json --output example-plan.md
```

Open `example-plan.md` to read each move's mechanism, concrete move, why
overlooked, 48-hour test, success signal, stop condition, evidence status,
and bounds, followed by the declared sources section and the single
`prioritized_action`. The Markdown escapes all authored text and never
follows source URLs.

## Recipe 2: Initialize a v0.2 draft, review it, and select one move

Without `--contract`, `init` copies the v0.2 bounded plan. Review the copy for repeated
mechanisms or unclear evidence labels, then record a declared selection in
a new validated revision.

```sh
python scripts/moves.py init --output draft.json
python scripts/moves.py review draft.json --output review.json
python scripts/moves.py select draft.json --move-id move-02 \
    --reason "Subtraction fits the available time" \
    --first-step "Prepare one private practice card" \
    --output selected.json
```

`select` requires `--move-id`, `--reason`, `--first-step`, and `--output`.
The output is a fresh plan revision with a new SHA-256 digest; the input
plan is unchanged.

## Recipe 3: Produce an experiment card and replay the synthetic outcome

A v0.2 plan is required. The card copies the selected move, its metric,
time bounds, success signal, stop condition, and rollback into a
`human_review_required` artifact.

```sh
python scripts/moves.py card draft.json --output card.json
python scripts/moves.py observation-draft draft.json --output observation.json
```

Edit `observation.json` only for real work. For the synthetic replay in
`examples/bounded-outcome.json`, the bound digest and move ID already match
`examples/bounded-plan.json`:

```sh
python scripts/moves.py outcome examples/bounded-plan.json examples/bounded-outcome.json \
    --output outcome-review.json
```

The result reports the declared numeric target separately from the stop
decision. The synthetic outcome reaches its numeric target but the active
time budget ends, so the decision is `stop_and_review`, not continuation.

## Recipe 4: Build a cumulative checkpoint history and export CSV

`record` validates the supplied observation and the full prior history
before creating a new file. The history is never rewritten; each
checkpoint file is a separate artifact. After two or more records, export
the validated history to a spreadsheet-safe CSV.

The `observation.json` draft from Recipe 3 starts unfilled, and its empty
notes deliberately fail validation. For this fictional walkthrough only,
set these fields and keep the generated digest, move ID, and other fields
unchanged. For real work, enter actual observations and leave an
unavailable value `null`.

```json
{
  "elapsed_hours": 24,
  "active_minutes": 10,
  "observed_value": 1,
  "notes": "Synthetic replay only, no experiment occurred."
}
```

Record the first checkpoint, then prepare a second draft bound to the same
revision:

```sh
python scripts/moves.py record draft.json observation.json --output checkpoints.json
python scripts/moves.py observation-draft draft.json --output observation-2.json
```

Times are cumulative, so the second checkpoint repeats the totals so far,
never just the new interval. Set these fields in `observation-2.json`:

```json
{
  "elapsed_hours": 48,
  "active_minutes": 20,
  "observed_value": 2,
  "notes": "Synthetic second checkpoint only, no experiment occurred."
}
```

```sh
python scripts/moves.py record draft.json observation-2.json \
    --history checkpoints.json --output checkpoints-2.json
python scripts/moves.py timeline draft.json checkpoints-2.json \
    --format csv --output checkpoints.csv
python scripts/moves.py limits draft.json checkpoints-2.json --output limits.json
```

The second checkpoint reaches both the declared active-time budget and the
experiment window, so the history ends in `stop_and_review` even though the
synthetic target is met.

Every row in `checkpoints.csv` keeps its plan digest, selected move,
cumulative and interval effort, metric, baseline, target, observed value,
progress, consent and stop declarations, original notes, and the human
review state. `limits.json` reports remaining declared bounds and any
overrun, clamped at zero, while earlier stop reasons persist.

## Recipe 5: Shortlist by declared bounds and audit source dates

`screen` finds moves whose declared active-time budget and exposure fit
your available scope. `sources` audits declared source dates against a
reference date you choose; no network request is made.

```sh
python scripts/moves.py screen draft.json --max-minutes 20 \
    --exposure self_only --max-start-hours 12 --max-duration-hours 24 \
    --output shortlist.json
python scripts/moves.py sources draft.json --as-of 2026-09-21 \
    --max-age-days 30 --output source-audit.json
```

`shortlist.json` preserves original move order, explains every exclusion,
and flags an out-of-scope selected move without replacing it.
`source-audit.json` distinguishes missing, invalid, future, and older
dates; dates within the threshold are not verified current sources.
Publisher identity, content, relevance, and high-stakes suitability still
need human review.

## Recipe 6: Import a prose skill response as a v0.1 plan

The skill answers in prose by default. Check the saved response's structure,
then transcribe it into a v0.1 plan for the other commands. The goal is
always yours: `import-response` never infers it from the framing.

```sh
python scripts/validate_response.py examples/example-response.md
python scripts/moves.py import-response examples/example-response.md \
    --goal "Make practice consistent during a fictional irregular week." \
    --output imported.json
python scripts/moves.py review imported.json --output imported-review.json
python scripts/moves.py render imported.json --output imported.md
```

The response passes only the structural check; its content is unverified.
`imported.json` has IDs `move-01` to `move-05` and is identical to
`examples/example-plan.json`, because that example response is its prose form.
A response with a Sources section needs `--sources` with a JSON array of
at least one declared source record, and `--high-stakes` also requires that
section. Prose citations are never parsed into sources. The input response is unchanged.

## Recipe 7: Promote a v0.1 plan to v0.2 with declared experiments

Version 0.2 needs a real experiment for every move. `experiments-draft`
writes an unfilled experiment object per move ID, with no number filled
in, so an unfilled draft fails `promote`. Fill every field with actual
baselines and bounds; if any baseline is unknown, stay in v0.1. This
walkthrough continues from Recipe 6 and uses
`examples/promote-experiments.json`, the **fictional** experiments of
`examples/bounded-plan.json`, whose move IDs match the imported plan.

```sh
python scripts/moves.py experiments-draft imported.json --output experiments.json
python scripts/moves.py promote imported.json \
    --experiments examples/promote-experiments.json --move-id move-01 \
    --reason "Cue timing is the cheapest uncertainty to test" \
    --first-step "Pick the existing daily cue" --output promoted.json
python scripts/validate_plan.py promoted.json
python scripts/moves.py compare imported.json promoted.json --output promotion-changes.json
python scripts/moves.py card promoted.json --output promoted-card.json
```

`promoted.json` is a new v0.2 revision: every move gains its declared
experiment, `selected_move_id` is set, and `prioritized_action` reads
`Selected move-01. Reason: ... First step: ...`, as `select` writes it.
Every other field is copied unchanged and `imported.json` is not modified.
`promotion-changes.json` flags the contract version, selection, and each
new experiment for review. The numbers are synthetic, not measurements, and
the selection records no approval.
