# Local plan workflow

Use Python 3.11 or later. All commands use the standard library and make no network requests. From the repository or extracted package root:

```sh
python scripts/moves.py init --output draft.json
python scripts/validate_plan.py draft.json --json
```

The initial draft is a complete synthetic language-practice example. Replace its goal, all five moves, assumptions, and numeric bounds before treating it as your plan. The tool copies an example; it does not generate personalized strategy. Output creation refuses to overwrite an existing file. The same commands work as `python -m scripts.moves` from the repository root.

Version 0.1 remains supported. See the [experiment contract](experiment-contract.md) for the additive version 0.2 fields.

## Review the portfolio

```sh
python scripts/moves.py review draft.json --output review.json
```

Review reports flag exact repeated mechanisms, actions, and tests after case and whitespace normalization, plus unclear evidence labels. No finding means only that these narrow checks found nothing. The report always leaves human review incomplete and includes concrete review questions. It never ranks by an invented numeric quality score. High-stakes sources require human verification even when structurally valid.

## Read or share a review copy

```sh
python scripts/moves.py render draft.json --output draft.md
```

The renderer includes all moves, bounds, evidence, sources, and exactly one prioritized action. User-supplied Markdown and HTML are escaped and line breaks inside values become spaces. It does not follow source URLs, embed remote content, or publish the report. Keep the JSON as the editable source.

## Prepare the selected experiment

```sh
python scripts/moves.py card draft.json --output card.json
```

Version 0.2 cards copy the single selected move, its metric, time bounds, success signal, stop condition, and rollback. They always start in `human_review_required`. A canonical SHA-256 of the plan binds later observations to that exact revision. This is a consistency check, not proof of authorship or an immutable record. Review consent, authority, sources, and actual baseline before starting any test yourself.

## Review reported observations

```sh
python scripts/moves.py outcome draft.json observation.json --output outcome-review.json
```

Use the [outcome schema](../schemas/outcome.schema.json). Copy `plan_sha256` and `move_id` from the card, report elapsed hours, active minutes, observed metric value (or `null` when unavailable), whether the stop condition triggered, actual consent status, and honest notes. Never invent a measurement to complete a field.

The result separately reports whether the declared numeric target was met. A triggered stop, reached time bound, or missing required consent produces `stop_and_review` even if the target was met. Otherwise the result is `review_observation`, never automatic continuation. Numeric target attainment does not prove causation or satisfy every qualitative success signal. Changed plan revisions and selected moves are rejected. High-stakes source review remains required.

## Compare revisions before a new trial

Outcome reviews include the declared metric, baseline, target, direction, and observed value. `change_from_baseline` and `progress_fraction` are decimal strings computed to 28 significant digits (or `null` without a measurement), so extreme finite inputs cannot turn into JSON infinity. A fraction of 1 reaches the numeric target, a negative fraction moves away, and values above 1 exceed it. This is descriptive progress, not evidence of causation or permission to continue.

To avoid copying the wrong digest or move ID, prepare a revision-bound observation draft:

```sh
python scripts/moves.py observation-draft draft.json --output observation.json
```

The draft starts with an unavailable measurement, zero elapsed/active time, false consent/stop flags, and empty notes. Replace these fields with actual observations. Empty notes deliberately fail outcome validation; the draft is not recorded evidence or consent confirmation.

Record your choice in a separate validated revision instead of manually synchronizing the selected ID and action:

```sh
python scripts/moves.py select draft.json --move-id move-02 --reason "Fits available practice time" --first-step "Review the private practice setup" --output revised.json
```

Selection never ranks or starts a move. It requires a human reason and first step, preserves the input, and changes the plan digest. Create a fresh card and observations for that revision.

```sh
python scripts/moves.py compare draft.json revised.json --output changes.json
```

The report matches moves by ID, distinguishes reordering from content changes, and shows before/after values for changed experiment bounds, sources, selected action, and goal. Keep IDs stable when revising a move. Replacing a mechanism entirely can justify a new ID. Review any changed limits or exposure before another trial. A diff reports change, not improvement.
