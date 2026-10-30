# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The root `VERSION` file is the single source of the package version, and
`scripts/validate.py` checks that the newest dated release below matches it.

## [Unreleased]

### Added

- Add `scripts/validate_response.py`, a structural checker for the skill's prose output. It checks five to seven `### Idea N: Title (mechanism)` blocks numbered from 1, the seven labeled fields in order with visible text, a Sources section after the ideas and before the end, and exactly one closing prioritized action paragraph with nothing after it. A Sources section is an ATX or setext heading of any level titled Sources, or a line that starts with a bold or plain Sources label, so a `**Sources:** ...` line attached to the final paragraph is reported as Sources after it instead of being read as part of the action. Every line Markdown renders inside a bullet joins its field, including unindented continuation lines and indented paragraphs after a blank line, and wrapped priority lines join that paragraph. Lines end only at LF, CRLF, or CR, so U+2028 and similar characters cannot split text out of a field. Fenced code is ignored, and a fence closes only on a run of its own character at least as long as the opening one. Matching takes time linear in the line length, so a long run of spaces cannot stall the check within the 1 MB bound, and the same lexical screen as the plan validator covers the action, test, signal, stop, and priority text. `--high-stakes` also requires Sources, `--json` prints a machine report, and a refusal or limitation is reported as not a completed plan. Exit 0 means a valid shape, 1 an invalid or unreadable file, 2 bad arguments. Until now only JSON output had a deterministic check, so a prose answer with Sources after the final action, the defect class fixed in 0.3.0, went unnoticed. All 12 revised completed responses in the recorded probe pass, and the two baseline responses with that defect fail on it. `examples/example-response.md` is the prose form of `examples/example-plan.json`, and `scripts/check.py` now runs eight checks, including this one on that example.
- Add `moves.py import-response RESPONSE.md --goal TEXT --output PLAN.json [--high-stakes] [--sources SOURCES.json]`, which transcribes a structurally valid prose response into a new version 0.1 plan: Idea N becomes `move-NN`, the heading gives the title and mechanism, the seven labeled fields map to the plan fields, and the final paragraph becomes `prioritized_action`. The skill answers in prose, but every offline command needs JSON and `init` only copies a synthetic example, so tracking a real answer meant hand-copying 35 to 63 values. The command refuses (exit 1, no file) a response that fails the structural check, takes the goal only from `--goal`, never parses prose citations (a response with a Sources section needs at least one declared record in `--sources`, so an empty array is refused), validates the result as an ordinary plan, and never overwrites. The help text says the plan is a transcription and nothing in it is verified. Importing `examples/example-response.md` reproduces `examples/example-plan.json` byte for byte, all 12 revised completed recorded responses import into valid plans, and a sixth usage recipe chains the checker, the import, `review`, and `render`.
- Add `moves.py init --contract {v0.1,v0.2}`, `experiments-draft`, and `promote`, so the CLI covers both ends of the documented path from v0.1 (unknown baselines) to v0.2 (measured experiments). `init --contract v0.1` copies `examples/example-plan.json`; without the flag `init` writes exactly what it wrote before. `experiments-draft PLAN --output FILE` writes an unfilled experiment for every move with no number defaulted, so an unfilled draft fails. `promote PLAN --experiments FILE --move-id ID --reason TEXT --first-step TEXT --output OUT` requires a v0.1 plan and exactly one experiment per move ID, checks each with the v0.2 experiment rules, and writes a new v0.2 revision with the experiments copied exactly, the selected move set, and the prioritized action written as `select` writes it. The input is never modified and an existing output is never overwritten. Both commands refuse a v0.2 input, and `moves_cli.py` refuses it earlier through a new `V01_REQUIRED_COMMANDS` gate. Until now users hand-edited ten experiment fields into every move. `examples/promote-experiments.json` reuses the fictional experiments of `examples/bounded-plan.json`, and a seventh usage recipe promotes the plan imported in the sixth.
- Add `verify-handoff --diff`. On a mismatch it writes `consistent: false`, every differing path (such as `outcome_review.measurement.progress_fraction` or `timeline_review.checkpoints[0].review.reasons[0]`) with its change (`changed`, `missing`, or `unexpected`), the stored and recomputed values, and the advice to rebuild with `handoff` rather than edit records, then exits 1. When the plan digest does not match, the paths are `plan_sha256` and every card and review path recomputed from the stored plan; observations are not recomputed against an edited plan, because each record is bound to the digest it was written against. A consistent bundle prints the same report as before. Values are compared with the same JSON serialization as the whole-bundle check, so `1` and `1.0` differ and the list is never empty for a failing bundle.
- Add a corpus of handoffs written by the 0.3.0 release code in `tests/fixtures/v0.3.0/`: a plan-only and an observation `handoff-v0.1` (with a 34-digit progress string), the replay `handoff-v0.2`, a `handoff-v0.2` covering 0.3.0's widened precision (a baseline of 1e30 with an observed 2e-5, elapsed hours 0.2 then 0.3, unconfirmed consent), and a `record`-built history with its plan. Each was generated from an export of tag `v0.3.0` and checked with its own `verify-handoff`; the README records the commands and `SHA256SUMS` the digests. `tests/test_compat.py` verifies and restores every handoff, extends the history with `record`, and checks the digests, so a later change to a derived string can no longer silently reject bundles users exported with 0.3.0, as a decimal precision change once did. CONTRIBUTING's release steps say to add a new corpus when a release changes a derived string and never to edit an older one.
- Add `scripts/install_skill.py (--project DIR | --dest DIR) [--check] [--json]`. Installing the skill was a manual copy with safety rules (a new destination, no merge or overwrite, `SKILL.md`, `agents/openai.yaml`, and all of `references/` together) that nothing performed or checked. The installer copies exactly the skill files listed in `package-manifest.json` into `DIR/.agents/skills/unconventional-moves` or an explicit `--dest`, refuses any existing destination including an empty directory or a symlink (and names a file standing where `.agents` or `.agents/skills` should be), checks every staged file against its source, re-checks the destination, and publishes with one directory rename, so a failure leaves nothing behind. `--check` writes nothing and reports each installed file as identical, changed, missing, or extra, exiting 0 only for an identical copy. It has no default destination, reads no environment variable, never overwrites, merges, or deletes, and works from a checkout or an extracted package. README documents the upgrade path (check, back up, move the old copy yourself, install) and SECURITY.md what it writes, including the hidden staging directory a hard crash can leave.

### Changed

- Name what failed when a handoff does not verify. `verify-handoff` and `unpack-handoff` used to give one generic message for any recomputed difference, and a bundle whose plan was edited after export got an observation message pointing to `observation-draft`. They now report, in order, the unchanged structure and plan messages, `handoff plan_sha256 does not match the plan; the plan or its stored digest was changed after the bundle was written` followed by `plan_sha256` and each card and review path that differs when recomputed from the stored plan (the message does not claim which of the two was edited), `handoff observation is invalid: ...` (or `observations are invalid` for a timeline), and for a derived difference the existing message followed by up to five differing paths and `and N more`. Exit codes, the success report, and both handoff formats are unchanged, and `unpack-handoff` still creates no directory on failure.

### Fixed

- Report a checked file that is not UTF-8 as a failure instead of raising `UnicodeDecodeError`. `scripts/validate.py` decoded `SKILL.md`, `README.md`, `agents/openai.yaml`, `schemas/moves.schema.json`, and `examples/adversarial-fixtures.json` without an encoding guard, so a single non-UTF-8 byte ended the repository gate with a Python traceback instead of a diagnostic. The Markdown link check already reported this condition; the remaining read paths report it the same way and the run continues, so every other check still runs and reports.
- Report repository JSON of an unexpected shape as a failure instead of raising. `scripts/validate.py` assumed the shapes of `schemas/moves.schema.json` and `examples/adversarial-fixtures.json`, so valid JSON such as an array-form `items` or a non-array `required` in the schema, a fixture case that is not an object, or a fixture ID that is not a string ended the repository gate with an `AttributeError` or `TypeError` traceback. These now fail the existing schema checks or a new `adversarial fixtures are objects with string IDs` check, and the run continues.
- Report an eval fixture tag that is a list or an object as a case failure. `evals/runner.py` checked tag uniqueness with `set()` before checking tag types, so such a tag raised `TypeError` and stopped the runner with a traceback instead of printing `FAIL` for that case.
- Point the release links at the end of this changelog at commits that exist. The `v0.1.0` and `v0.2.0` tags were never created, so the 0.1.0, 0.2.0, and 0.3.0 links returned 404. They now name the 0.1.0 release commit and the merge that first set `VERSION` to 0.2.0.

## [0.3.0] - 2026-10-09

This is the first release since 0.2.0. Archives built from `main` between 2026-09-09 and this release were named 0.2.0 but contained later changes. A `0.3.0` heading added to this file earlier was never released; its entries are part of this release.

### Added

- Add a tag-triggered release workflow. For a `vX.Y.Z` tag it checks that the tag matches `VERSION` and a dated CHANGELOG section (`scripts/versioning.py --check-tag`), reruns the check set, builds the archive and checksum, records a GitHub build provenance attestation for the archive, and publishes a GitHub Release whose notes are that CHANGELOG section (`--notes`). CONTRIBUTING documents the release steps, and tests keep workflow expressions out of run scripts.
- Add `--version` to `moves.py`, `moves_cli.py`, `validate_plan.py`, `validate.py`, `package.py`, and `check.py`. It prints `unconventional-moves X.Y.Z` from the root `VERSION` file, including from an extracted archive, and exits 1 with a clear message when `VERSION` is invalid.
- Add `scripts/check.py`, which runs the CI check set in order (repository validation, both example plan validators, the outcome replay, the unit tests, the eval fixture runner, and a package build into a temporary directory) and stops at the first failure. CI now runs this one script, and README, CONTRIBUTING, and the eval README point to it; `--list` prints the commands.
- Check in `scripts/validate.py` that this changelog keeps `[Unreleased]` first, lists dated releases from newest to oldest, and names `VERSION` as the newest release.
- Add `unpack-handoff` to verify a handoff before restoring its exact plan and complete supplied checkpoint history into a new directory, with persistent stop decisions and pending human review.
- Include a runnable synthetic recovery and revision walkthrough, clean extracted-package coverage, and the documented version-aware CLI shim in the package.
- Export checkpoint histories as spreadsheet-safe CSV with measurements, exact progress strings, original notes, and persistent stop decisions.
- Add a frozen behavioral rubric and 20 synthetic cases, separating offline fixture checks from optional model review.
- Record validated cumulative histories without replacing earlier files.
- Review exact checkpoint intervals, effort, missing measurements, target regressions, and remaining bounds.
- Filter declared start and duration windows and identify repeated source support.
- Export spreadsheet-safe portfolio tables, whole-history handoffs, and inert Markdown debriefs.

### Changed

- Align the pull request template with CONTRIBUTING: drop the issue-form front matter that appeared as literal text in new pull requests, and replace a checklist that forbade CHANGELOG and CI edits with the actual contribution checks. Bug reports now ask for `--version` output, Python version, the exact command, and its exit code, and a security contact link points to the security policy.
- Run CI on Python 3.11, 3.12, 3.13, and 3.14 on Ubuntu and Windows with Node 24 releases of `actions/checkout` and `actions/setup-python` pinned to full commit SHAs, checkout credentials not persisted, `fail-fast` off, a 20 minute timeout, and superseded pull request runs cancelled. Pushes run CI only on `main`, so a pull request branch is no longer checked twice. Dependabot proposes weekly grouped action updates, and a test requires every workflow action to be pinned to a full commit SHA with a version comment.
- Check `screen` ceilings, `sources --max-age-days`, and `sources --as-of` when arguments are parsed, so an out-of-range number, a non-ASCII digit, or an impossible date exits 2 as the documented exit-code contract says, instead of 1 after reading the plan. File errors now say whether the input could not be read or the output could not be created.
- Pin LF line endings in `.gitattributes`, so a Windows checkout with Git's default `autocrlf` packages the same file contents as a Unix checkout, and test that every packaged file is LF and every tracked file is either packaged or deliberately repository-only.
- Ship the eval runner and its per-case fixtures in the package so the documented fixture check can run from an extracted archive.
- Align revision diffs with digest representations and flag changed mechanisms, causal explanations, and tests for review.
- Strengthen causal diversity, contextual framing, experiment measurement, and one defensible first action without expanding the plan contracts.
- Resolve Sources ordering and distinguish declared selection from human approval.
- Configure CI for Python 3.11 and 3.12 on Windows and Ubuntu.
- Preserve pending human authority, persistent stop reasons, and unsigned evidence limits.

### Fixed

- Correct the documentation: the version decision tree no longer credits the JSON Schemas with rules only `scripts/validate_plan.py` enforces (an existing selected move, unique IDs, a source for high-stakes plans, case-insensitive URL schemes); the usage recipes say they call `moves.py` directly; Recipe 4 now shows the synthetic observation values and creates its second observation, so it runs; and two misfiled local workflow sections are moved under the right headings. `tests/test_docs.py` executes every usage recipe and the README offline workflow.
- Limit the repository check's dash, safety, and link scans to project files, skipping version control, build output, tool caches, and any directory holding a `pyvenv.cfg`, so an in-repo virtual environment no longer fails the check; a Markdown file that is not UTF-8 is now reported as a failure instead of raising `UnicodeDecodeError`.
- Report `move_order_changed` in `compare` only when moves kept in both revisions change their relative order, instead of whenever a move is added or removed.
- Group a bare-host source URL such as `https://example.test` with the same URL ending in `/` in the source audit.
- Keep progress, checkpoint interval, and remaining bound arithmetic exact across operand magnitudes. Each calculation keeps the precision 0.2.0 used unless that precision rounds a difference, so derived strings stay identical to earlier output for ordinary inputs, and `verify-handoff` and `unpack-handoff` still accept bundles written by 0.2.0. Where 0.2.0 rounded a difference, or displayed a progress fraction of 1 for a value that is not the target, precision widens to the combined magnitude range of the operands: a baseline of 1e30 with an observed 2e-5 no longer displays 1 for a missed target, and an interval overrun of 6e-299 minutes is rejected instead of rounded away. A bundle that carries one of those rounded strings now fails `verify-handoff`; regenerate it with `handoff` from its source plan and observations instead of editing any record.
- Write UTF-8 standard output from `validate_plan.py`, `validate.py`, and the eval runner, so a valid plan under a path the console encoding cannot represent passes instead of exiting 1 with `UnicodeEncodeError`.
- Reject control and format characters in repository link paths before resolving them, so the link check fails closed on every Python version instead of relying on `Path.resolve()` raising for NUL, which Python 3.13 and 3.14 on Windows no longer do.
- Return exit code 2 when the eval rubric file is missing, instead of raising FileNotFoundError.
- Reject NaN, Infinity, and non-finite numbers in eval fixtures instead of accepting Python's non-JSON constants.
- Report a non-object eval fixture as a case failure instead of crashing while formatting the error.
- Reject duplicate keys in repository JSON checked by the validator, instead of keeping the last value.
- Group declared publisher names that differ only by format characters such as a zero-width space, so repeated support is not hidden.
- Flag an added or removed experiment object in revision review triggers, matching the other measurement changes.
- Compute progress and change from baseline with enough decimal precision to represent the parsed numbers, so a huge gap cannot round to a fraction of 1.
- Reject plural forms of the screened actions, including laws, consents, scopes, and safeties, without flagging consenting participants or stealth.
- Reject required plan, outcome, and selection text that contains only whitespace or invisible format characters.
- Reject source URLs that contain control or format characters, including C1 controls, zero-width spaces, and bidi overrides.
- Check `file://` links that include a host against the repository boundary. A host no longer makes that URL look external.
- Reject duplicate keys in eval case files and the declared suite instead of silently keeping the last value.
- Remove a partially written report when output creation fails, so a retry is not blocked by the incomplete file.
- Group repeated source citations that differ only by a default port, an empty port, or IPv6 host case.
- Recognize the plural evidence labels `facts` and `sources` in review, matching the worksheet vocabulary and the other label stems.
- Return exit code 2 from the eval runner when the suite shape is wrong and no individual case failed, matching the runner contract.
- Fail the repository link check when a destination contains an encoded null, instead of crashing with ValueError.
- Apply the version gate to the first positional plan path, so flags placed before the plan still refuse a v0.1 plan on v0.2-only commands.
- Parse plan files at the version gate with the same bounded reader as the CLI, so deep nesting and non-finite numbers fail cleanly instead of raising RecursionError.
- Refuse a version 0.1 plan at the version gate for every command that reads the selected move, instead of failing later with a generic workflow message.
- Reject explicitly supplied null observations instead of silently exporting plan-only handoffs.
- Recognize narrow prevention language without globally exempting negated text; reject malformed Unicode, nesting, and numeric overflow.
- Align decimal target validation and outcome comparison; avoid empty reports on encoding failure.
- Reject ambiguous package paths and symlink ancestors; include rerunnable tests and verify deterministic same-environment builds.

## [0.2.0] - 2026-09-09

### Added

- Add compatible bounded experiment plans with an explicit selected move.
- Add local authoring, review, Markdown rendering, experiment cards, outcome review, and revision comparison.
- Keep stop conditions and human source, consent, and authority review explicit.
- Bundle schemas inside the installable skill and verify extracted-package workflows.
- Bound JSON reads and support machine-readable validation diagnostics.

## [0.1.0] - 2026-08-03

### Added

- Added deterministic five to seven move contract validation.
- Added required success signals, stop conditions, and exactly one prioritized action.
- Added a human non-obviousness rubric and adversarial behavioral fixtures.
- Added high-stakes Sources guidance, JSON schema mode, and a copy-ready worksheet.
- Added deterministic packaging, checksums, CI, and installation guidance.

[Unreleased]: https://github.com/EauDoon/unconventional-moves/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/EauDoon/unconventional-moves/compare/389dfc63ca09deeef85989a11db87e02b5327de5...v0.3.0
[0.2.0]: https://github.com/EauDoon/unconventional-moves/compare/72566a4ef515578e912db454088c0c5f988f7968...389dfc63ca09deeef85989a11db87e02b5327de5
[0.1.0]: https://github.com/EauDoon/unconventional-moves/tree/72566a4ef515578e912db454088c0c5f988f7968
