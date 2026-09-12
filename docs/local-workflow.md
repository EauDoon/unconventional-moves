# Local plan workflow

Use Python 3.11 or 3.12. These are the CI matrix versions; newer Python versions are unverified. All commands use the standard library and make no network requests. From the repository or extracted package root:

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

The renderer includes all moves, bounds, evidence, sources, and exactly one prioritized action at the end. Sources precede that final recommendation. Version 0.2 reports show the declared selected ID alongside the free-text recommendation; reconciling their meaning remains a human check. Existing free-text plans are not invalidated by an unreliable string-matching heuristic. User-supplied Markdown and HTML are escaped and line breaks inside values become spaces. It does not follow source URLs, embed remote content, or publish the report. Keep the JSON as the editable source.

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

## Offline browser report

Open a portable offline report in a browser:

```sh
python scripts/moves.py render draft.json --format html --output review.html
```

The self-contained report has keyboard-accessible approach links, the selected move label, complete declared experiment bounds, and a print layout. It works at mobile widths and contains no scripts, remote resources, external links, account controls, or execution actions. Authored text is escaped; the browser content policy blocks remote loads and scripts. Sources remain plain declared text for human review. Markdown remains the default format.

## Portable handoff

Create and check a self-contained reviewer handoff:

```sh
python scripts/moves.py handoff draft.json --observation observation.json --output handoff.json
python scripts/moves.py verify-handoff handoff.json
```

Omit `--observation` for a plan-only handoff. The bundle contains the full plan, its digest, review/card, and optional raw observation plus recomputed outcome review. Verification validates the plan and observation and recomputes every derived field. It detects accidental or partial tampering, not authorship or an attacker who rewrites a consistent unsigned bundle. All human checks remain pending. The actual formatted bundle must fit the same 1 MB JSON input bound, allowing a write/read roundtrip. Output files are never overwritten.

An explicitly supplied observation must be a completed outcome object. A file
containing `null` is rejected before creating output; it cannot silently turn a
requested observation handoff into a plan-only handoff. Existing plan-only bundles
retain their `null` observation and remain supported by `verify-handoff`.

Use `handoff draft.json --timeline checkpoints.json --output history-handoff.json` to include the entire supplied cumulative history in a version 0.2 handoff. `--timeline` and `--observation` are mutually exclusive. `verify-handoff` accepts both versions and recomputes the timeline review plus an observation digest that covers notes as well as numbers. Earlier stops cannot be hidden by only exporting the latest derived review. The tool cannot detect omitted historical records or a fully rewritten consistent unsigned bundle, so reviewers must still establish completeness themselves.

## Printable card

Export a focused printable card with all declared experiment bounds, rollback, stop condition, digest, and unchecked human review checklist:

```sh
python scripts/moves.py card draft.json --format markdown --output experiment-card.md
```

JSON remains the default for existing callers. Markdown escapes authored content and includes the recorded reason/first step. Checkboxes are prompts for a human, not stored approvals or a start control.

## Revision review triggers

Revision comparisons now include `review_triggers` for changed scope, selected action, evidence, measurements, stop/success conditions, and added or removed moves. Expanded declared time bounds are called out separately. `observation_binding_changed` identifies when old observations no longer match the revision, including reorder-only changes. An empty trigger list does not certify that the change is safe; every changed plan still needs review.

Changes to a mechanism, its causal explanation, or the 48-hour test also trigger
review in both plan versions. Field comparisons use the same canonical parsed
JSON representation as the plan digest: changing `0` to `0.0` or `0.0` to `-0.0`
is visible because it changes the observation binding, even when the numeric
meaning is equivalent. JSON whitespace and object key order do not count as
revisions. Original numeric spelling beyond what JSON parsing preserves is not
compared.

## Constraint shortlist

Find moves whose declared active-time budget and participant exposure fit your available scope:

```sh
python scripts/moves.py screen draft.json --max-minutes 20 --exposure self_only
```

The report preserves original order, explains every exclusion, and flags an out-of-scope selected move without replacing it. The `consenting_participants` ceiling includes self-only moves too; it does not establish that anyone consented. Use `select` to record a choice after review; the command cannot authenticate who supplied it.

Add `--max-start-hours 12 --max-duration-hours 24` to exclude declared start windows or experiment durations beyond your available window. A start ceiling of zero accepts only immediate-start declarations. These optional filters leave older command behavior intact and do not reschedule a move or prove that its latest start is feasible.

## Declared source dates

Audit declared source dates against a reference date and age threshold you choose:

```sh
python scripts/moves.py sources draft.json --as-of 2026-09-10 --max-age-days 30
```

Missing, invalid, future, and older dates are distinguished. A date within the threshold is not a verified current source. No network request occurs; publisher identity, content, relevance, and high-stakes suitability still need human verification. The explicit reference date makes the report reproducible.

The source audit also groups repeated URLs (ignoring fragments and host case) and equal declared publisher names (ignoring case and repeated whitespace). Groups use the original one-based source positions and preserve every citation. Different URL paths and queries remain distinct. These prompts identify possible repeated support; neither an empty group list nor different publisher names establish independent evidence.

## Cumulative checkpoints

Review several checkpoints from one revision and selected move:

```sh
python scripts/moves.py timeline draft.json checkpoints.json --output timeline-review.json
```

`checkpoints.json` is an array of 1 to 100 completed outcome records in increasing elapsed-hour order. Active minutes are cumulative and cannot decrease. Each record must match the current digest and move. Any earlier stop reason remains in the final decision, even if a later record clears its flag. Entries recorded after the first stop are identified for human review. The report does not schedule, combine independent trials, or authorize continued activity.

Checkpoint interval checks use decimal arithmetic so a six-minute activity increase from 0.2 to 0.3 elapsed hours is accepted exactly. Even a small declared overrun of that interval is rejected.

The shared outcome validator also compares cumulative elapsed time in decimal, accepting exactly 1.8 active minutes at 0.03 elapsed hours across outcome, record, timeline, and handoff commands. It rejects actual excess instead of adding a tolerance that could hide it.

Each timeline row includes decimal-string interval hours, active minutes, and activity fraction. The first interval begins at zero; a zero-length initial interval has a `null` fraction. Later idle intervals report zero activity. These describe reported effort, not productivity or an instruction to use the remaining time.

### Export checkpoint history to a spreadsheet

```sh
python scripts/moves.py timeline draft.json checkpoints.json --format csv --output checkpoints.csv
```

The CSV contains one row per checkpoint in chronological order, including the
plan digest, selected move, cumulative and interval effort, metric, baseline,
target, observed value, progress, consent/stop declarations, and original notes.
Each row's decision and stop reasons retain every stop reached at or before that
checkpoint. Later target attainment cannot clear an earlier stop; later stops
are not applied retroactively to earlier rows.

Missing measurements and unavailable fractions are empty cells. Use
`measurement_available` to distinguish an unmeasured checkpoint from a measured
zero; `target_met` is empty when unmeasured. Exact decimal strings and all other
text cells have an apostrophe prefix to prevent spreadsheet formulas and preserve
their representation. Numeric observation fields remain numeric, so spreadsheet
software may round large values; keep the JSON history as the source record.
Every row retains `human_review_required`. The entire history is validated before
output is created, and existing files are never overwritten. JSON remains the
default format and existing handoffs are unchanged.

## Measurement context

Use `python scripts/moves.py record draft.json observation.json --output checkpoints.json` to begin a checkpoint history. Add `--history checkpoints.json --output next-checkpoints.json` for the next observation. The complete history is validated before a new file is created. Existing history is never rewritten. Reports may retain honest after-stop observations; recording one does not authorize activity after a stop.

An explicitly supplied history must be a JSON array, including `[]` for an intentionally empty history. `null` is rejected instead of silently starting over.

## Measurement interpretation

Outcome reviews include the declared metric, baseline, target, direction, and observed value. `change_from_baseline` and `progress_fraction` are decimal strings computed to 28 significant digits (or `null` without a measurement), so extreme finite inputs cannot turn into JSON infinity. A fraction of 1 reaches the numeric target, a negative fraction moves away, and values above 1 exceed it. This is descriptive progress, not evidence of causation or permission to continue.

## Observation drafts

Timeline `measurement_summary` identifies missing checkpoints, the first reported numeric target attainment, and every later measured checkpoint below that target. Missing data is never treated as attainment or regression. Attainment after an earlier stop is flagged and cannot clear the stop. These are descriptive checkpoints, not independent samples or proof of durable improvement.

To avoid copying the wrong digest or move ID, prepare a revision-bound observation draft:

```sh
python scripts/moves.py observation-draft draft.json --output observation.json
```

The draft starts with an unavailable measurement, zero elapsed/active time, false consent/stop flags, and empty notes. Replace these fields with actual observations. Empty notes deliberately fail outcome validation; the draft is not recorded evidence or consent confirmation.

## Remaining bounds

Use `python scripts/moves.py limits draft.json checkpoints.json` to review the latest cumulative elapsed hours and active minutes against both declared limits. Remaining amounts and overruns are separate decimal strings, clamped at zero. The complete history is validated and earlier stop reasons persist even when a numeric budget remains. This report provides no continuation allowance.

## Explicit selection

Record your choice in a separate validated revision instead of manually synchronizing the selected ID and action:

```sh
python scripts/moves.py select draft.json --move-id move-02 --reason "Fits available practice time" --first-step "Review the private practice setup" --output revised.json
```

Selection never ranks or starts a move. It requires a supplied reason and first step, preserves the input, and changes the plan digest. These declarations do not authenticate a human chooser or approval. Create a fresh card and observations for that revision.

## Portfolio table

Use `python scripts/moves.py table draft.json --format csv --output portfolio.csv` to compare declared metrics, baselines, targets, start windows, durations, active-time budgets, exposure, and rollback in a spreadsheet. JSON is the default and preserves exact authored strings. CSV uses standard quoting and prefixes all text cells with an apostrophe to prevent spreadsheet formulas; numeric cells remain numeric. Each row retains its plan digest, declared-selection flag, and pending human-review state. Original move order is preserved; different metrics cannot be ranked as if their numbers were comparable.

## Experiment debrief

Use `python scripts/moves.py debrief draft.json checkpoints.json --output debrief.md` for a review copy with the selected hypothesis, each reported observation and note, missing measurements, target regressions, earlier stops, remaining bounds, rollback, and declared sources. Authored Markdown and HTML are escaped. The complete history is validated before rendering. Learning questions remain human judgments; the report neither invents conclusions nor records approval, completed rollback, consent verification, or a decision to run another trial.

## Compare revisions before a new trial

```sh
python scripts/moves.py compare draft.json revised.json --output changes.json
```

The report matches moves by ID, distinguishes reordering from content changes, and shows before/after values for changed experiment bounds, sources, selected action, and goal. Keep IDs stable when revising a move. Replacing a mechanism entirely can justify a new ID. Review any changed limits or exposure before another trial. A diff reports change, not improvement.

## Replay a complete synthetic history

From a fresh extracted package root, run these commands with unused output names:

```sh
python scripts/moves.py init --output draft.json
python scripts/moves.py review draft.json
python scripts/moves.py select draft.json --move-id move-01 --reason "Synthetic replay: test cue timing first" --first-step "Privately review the next existing cue" --output selected.json
python scripts/moves.py card selected.json --output card.json
python scripts/moves.py observation-draft selected.json --output observation.json
```

For this fictional replay only, edit `observation.json`: set `elapsed_hours` to
`24`, `active_minutes` to `10`, `observed_value` to `1`, and `notes` to
`Synthetic replay only, no experiment occurred.` Keep the generated revision
hash, move ID, and other fields unchanged. For real work, enter actual observations
and actual consent/stop declarations instead; leave an unavailable value `null`.

```sh
python scripts/moves.py outcome selected.json observation.json
python scripts/moves.py record selected.json observation.json --output checkpoints.json
python scripts/moves.py timeline selected.json checkpoints.json
python scripts/moves.py debrief selected.json checkpoints.json --output debrief.md
python scripts/moves.py handoff selected.json --timeline checkpoints.json --output handoff.json
python scripts/moves.py verify-handoff handoff.json
```

The synthetic target is not met, and the result requires review. A zero exit
status means report creation succeeded, never experiment success or approval.
To add another observation, create a new draft, enter cumulative times and honest
notes, then use `record` with `--history checkpoints.json` and a fresh output
name. A revision mismatch requires a new card/draft for the current plan;
retain earlier observations with their original plan rather than rebinding them.
