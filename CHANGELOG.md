# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The root `VERSION` file is the single source of the package version, and
`scripts/validate.py` checks that the newest dated release below matches it.

## [Unreleased]

### Added

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

- Pin LF line endings in `.gitattributes`, so a Windows checkout with Git's default `autocrlf` packages the same file contents as a Unix checkout, and test that every packaged file is LF and every tracked file is either packaged or deliberately repository-only.
- Ship the eval runner and its per-case fixtures in the package so the documented fixture check can run from an extracted archive.
- Align revision diffs with digest representations and flag changed mechanisms, causal explanations, and tests for review.
- Strengthen causal diversity, contextual framing, experiment measurement, and one defensible first action without expanding the plan contracts.
- Resolve Sources ordering and distinguish declared selection from human approval.
- Configure CI for Python 3.11 and 3.12 on Windows and Ubuntu.
- Preserve pending human authority, persistent stop reasons, and unsigned evidence limits.

### Fixed

- Size decimal precision from the combined magnitude range of all operands in progress, checkpoint interval, and remaining bound arithmetic, so a baseline of 1e30 with an observed 2e-5 no longer displays a progress fraction of 1 for a missed target, and an interval overrun of 6e-299 minutes is rejected instead of rounded away.
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

[Unreleased]: https://github.com/EauDoon/unconventional-moves/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/EauDoon/unconventional-moves/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/EauDoon/unconventional-moves/releases/tag/v0.1.0
