# Schema v0.1 versus v0.2 decision tree

Both contract versions remain supported. The choice is driven by the
schema constraints in `schemas/moves.schema.json` (v0.1) and
`schemas/moves-v0.2.schema.json` (v0.2), and by the version gate in
`scripts/moves_cli.py`. Pick the version that matches the evidence you
actually have, not the version you wish you had.

## Required top-level fields

Both schemas require `contract_version`, `goal`, `high_stakes`, `moves`,
`prioritized_action`, and `sources`, with `moves` constrained to five to
seven entries. Version 0.2 adds one required top-level field:
`selected_move_id` (non-empty string that names an existing move). If you
cannot point at exactly one chosen move, you are not ready for v0.2.

Sources follow the same shape in both versions: each entry has `title`,
`url`, and `supports`; `publisher` and `date` are optional. Both require
a nonempty `sources` array when `high_stakes` is true.

## Required move fields

Version 0.1 moves require exactly ten fields: `id`, `title`, `mechanism`,
`concrete_move`, `why_overlooked`, `test_48h`, `success_signal`,
`stop_condition`, `evidence_status`, and `bounds`. All are non-empty
strings, so bounds, success signals, and stop conditions are free text.

Version 0.2 moves require the same ten fields plus a required
`experiment` object. The `experiment` must contain exactly ten fields:
`hypothesis`, `metric`, `rollback`, `baseline`, `target`,
`start_within_hours`, `duration_hours`, `max_minutes`, `direction`, and
`exposure`. No v0.2 move is valid without every one of these filled.

## Experiment card constraints (v0.2 only)

The v0.2 `experiment` object pins the numeric and time shape of the test:

- `baseline` and `target` are finite numbers. The validator compares them
  with `Decimal`, so the target must strictly improve on the baseline in
  the declared `direction` (`increase` or `decrease`).
- `start_within_hours` is an integer from 0 to 48.
- `duration_hours` is an integer from 1 to 48.
- `max_minutes` is an integer from 1 to 2880 and cannot exceed
  `duration_hours * 60`.
- `exposure` is `self_only` or `consenting_participants`. The label
  declares intended exposure; it never establishes consent.

These checks supplement JSON Schema, which does not enforce cross-field
comparisons or unique move IDs. See
[experiment-contract.md](experiment-contract.md) for the full rules.

## CLI command gate (from scripts/moves_cli.py)

The version-aware shim reads `contract_version` from the plan at `argv[1]`
and refuses v0.2-only commands against a v0.1 plan with exit 1, before
`moves.py` runs.

- v0.2-only commands: `card`, `outcome`, `select`, `observation-draft`,
  `handoff`.
- Commands that accept either version: `debrief`, `table`, `record`,
  `review`, `render`, `screen`, `sources`, `limits`, `timeline`.
- Commands with no plan argument: `init`, `verify-handoff`.

The shim also refuses any `contract_version` outside the two supported
strings. Unknown versions do not pass through to `moves.py`.

## When to pick v0.1

- The brief is exploratory and you do not yet know a numeric baseline.
  Inventing a number to satisfy v0.2 produces an experiment card whose
  metric and target are unverified declarations, not measured evidence.
- You only need a free-text plan, a Markdown or HTML render, a review
  report, or a constraint shortlist. Every shared command accepts v0.1.
- The plan is high stakes and the only sources you can supply are
  declared, not verified. v0.2 would not improve the source situation
  and adds no new source field.

## When to pick v0.2

- You have a declared baseline and target for at least one move and can
  name exactly one selected move before the experiment starts.
- The test window fits the 0 to 48 hour start window and the 1 to 48
  hour duration window, with active minutes that fit inside the
  duration. v0.2 retains these as hard schema bounds.
- You plan to run `card`, `outcome`, `select`, `observation-draft`, or
  `handoff`, which require v0.2 at the CLI gate.
- You will record cumulative checkpoints, run `timeline`, export a CSV
  history, or build a portable v0.2 handoff bundle.
- A v0.2 plan still does not establish a verified chooser, approved
  action, or real measurement. The shape is stricter, not the safety
  net.