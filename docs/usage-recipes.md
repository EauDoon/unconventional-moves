# Usage recipes

Five copy-paste recipes that exercise the actual offline CLI. They use only
files and commands that ship in this repository: `examples/example-plan.json`
is a v0.1 plan, `examples/bounded-plan.json` is a v0.2 bounded plan, and
`examples/bounded-outcome.json` is a synthetic outcome bound to its plan
revision. Every recipe uses `python scripts/moves.py <command>` with flags
that exist in `scripts/moves.py` and the version gate in `scripts/moves_cli.py`.
Replace the output filenames when an artifact already exists. A successful
exit code only means a report was produced; it does not approve or start
anything.

## Recipe 1: Start from the synthetic v0.1 plan and render a Markdown report

The `init` command copies `examples/bounded-plan.json`, but for v0.1 the
example lives at `examples/example-plan.json`. Validate the existing file
first, then render an inert Markdown report.

```sh
python scripts/validate_plan.py examples/example-plan.json
python scripts/moves.py render examples/example-plan.json --output example-plan.md
```

Open `example-plan.md` to read each move's mechanism, concrete move, why
overlooked, 48-hour test, success signal, stop condition, evidence status,
and bounds, followed by the declared sources section and the single
`prioritized_action`. The Markdown escapes all authored text and never
follows source URLs.

## Recipe 2: Initialize a v0.2 draft, review it, and select one move

`init` always copies the v0.2 bounded plan. Review the copy for repeated
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

```sh
python scripts/moves.py record draft.json observation.json --output checkpoints.json
python scripts/moves.py record draft.json observation-2.json \
    --history checkpoints.json --output checkpoints-2.json
python scripts/moves.py timeline draft.json checkpoints-2.json \
    --format csv --output checkpoints.csv
python scripts/moves.py limits draft.json checkpoints-2.json --output limits.json
```

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