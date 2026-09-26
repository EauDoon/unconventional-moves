# Unconventional Moves

[![build](https://img.shields.io/github/actions/workflow/status/EauDoon/unconventional-moves/ci.yml?branch=main)](https://github.com/EauDoon/unconventional-moves/actions)
[![license](https://img.shields.io/github/license/EauDoon/unconventional-moves)](https://github.com/EauDoon/unconventional-moves/blob/main/LICENSE)
[![last commit](https://img.shields.io/github/last-commit/EauDoon/unconventional-moves)](https://github.com/EauDoon/unconventional-moves)

Turn a constrained goal into five to seven practical approaches that work through
different mechanisms, then choose one small experiment worth starting.

The skill separates the outcome from the assumed method, compares the ordinary
approach, and explains why each move could work here and what would make it fail.
Tests can begin within 48 hours; that does not promise proof in two days.

## Install and invoke

Copy `skill/unconventional-moves` from this repository into
`<project>/.agents/skills/unconventional-moves`. Keep `SKILL.md`,
`agents/openai.yaml`, and the complete `references/` directory together.
This project location follows the [Codex local skill documentation](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills).
If that destination already exists, compare or back it up before replacing it.
The installed skill needs no Python, CLI, account, or API key.

In that project's Codex session, invoke:

```text
Use $unconventional-moves for this goal: [desired outcome].
Constraints: [time, budget, resources, non-negotiables, affected people].
Current approach: [what we have tried and what seems stuck].
```

Implicit invocation is enabled for requests for non-obvious strategic options.
Routine factual questions, editing, translation, and execution do not call for a
portfolio of moves. If a missing answer materially changes the result, the skill
asks at most one focused question; otherwise it labels necessary assumptions.

Use the [worksheet](templates/worksheet.md) for a fuller brief or the
[synthetic prompts](examples/example-prompts.md) for examples across partnership
activation, product adoption, distribution, operations, and personal learning.

## Evaluation rubric

The skill is judged against a frozen behavioral rubric, not just structural
validation. Eight dimensions each score 0 to 2 with N/A for non-trigger or
refusal responses, and a critical failure is recorded separately for hard
constraint violations, fabricated evidence, instruction-following from
untrusted supplied material, unsafe actionable assistance, or false claims
of approval: mechanism distinctness, specificity and feasibility, constraint
adherence, experiment and measurement, evidence honesty, downside and third
parties, selected first action, clarity.

The full rubric, scoring rules, gates, and limitations live in
[evals/README.md](evals/README.md) and [evals/rubric.md](evals/rubric.md).
The offline `test_evals.py` integrity check confirms fixture IDs, splits,
fields, and declared coverage; it does not run a model or establish
usefulness. Structural validity never overrules the behavioral gates.

## What to expect

A brief framing identifies the bottleneck, resources, constraints, and desired
outcome. The conventional baseline is a comparison outside the move count;
unconventional does not automatically mean better.

Each idea uses this compact shape:

```text
### Idea N: Title (mechanism)

- Concrete move: Who does what with the available resources.
- Why overlooked: The hidden assumption or incentive, why this could work
  here, and the main failure condition.
- 48-hour test: The hypothesis and observation in a reversible test that
  can begin within 48 hours.
- Success signal: Evidence that would change the decision, not just activity.
- Stop condition: The result, risk, or time boundary that ends the test.
- Evidence status: Supplied facts, checked facts, inference, or speculation.
- Bounds: Meaningful time, cost, exposure, commitment limits, and rollback.
```

When sources are used, their section comes after the ideas and before the final
line. A normal completed response ends with exactly one:

```text
Prioritized action: One idea, its trade-off against the strongest alternative,
and its first concrete step.
```

Unsafe goals, contradictory constraints, or fewer than five feasible distinct
options warrant a refusal, limitation, or focused question. The skill must not
pad the answer or emit an invalid plan disguised as a completed result.

## Evidence and safety

Supplied claims are not independently checked facts. Inference and speculation
must remain visible; the skill must not invent research, measurements, consent,
source inspection, private access, or personal experience. Novelty never overrides
honesty, legality, consent, or meaningful bounds.

For health, safety, legal, financial, or similarly high-stakes claims, check
current reliable sources and prefer authoritative primary sources. A Sources
section lists title, publisher, date when available, URL, and the claim supported,
**before the final prioritized action**. If verification is unavailable, state
`Verification incomplete` and limit advice to source gathering or
non-consequential steps. Ordinary low-risk answers need no repeated source or
safety boilerplate.

## Optional offline workflow

The Python CLI authors and validates plans, renders review reports, and records
observations. It makes no model calls and executes no real-world experiments.
Use Python 3.11 or 3.12 (the CI matrix versions); `python` below means your verified interpreter (for
example, `py` on Windows or `python3` on Unix).

From a fresh copy of the repository or an extracted package, run:

```sh
python scripts/moves.py init --output draft.json
python scripts/moves.py review draft.json
python scripts/moves.py render draft.json --format html --output review.html
python scripts/moves.py card draft.json --output card.json
python scripts/moves.py outcome draft.json examples/bounded-outcome.json
```

This walkthrough replays a **fictional language-practice fixture**. Its numbers
are synthetic, not real measurements or a quality benchmark. The outcome fixture
matches the unchanged draft only. The fixture meets its numeric target but
returns `stop_and_review` because its bounds are reached. If the destination
files exist, use new filenames; report commands refuse overwrites.

For your own plan, replace the synthetic content, select one move, and create
new observation records bound to that plan revision. Follow the complete
[local workflow](docs/local-workflow.md) and [experiment contract](docs/experiment-contract.md)
for selection, checkpoints, history, handoffs, comparisons, and exports.

Checkpoint histories can also be exported with
`python scripts/moves.py timeline draft.json checkpoints.json --format csv --output checkpoints.csv`
for spreadsheet review of measurements, progress, notes, and persistent stops.
Missing measurements remain distinct from measured zero; JSON remains the source
record.

To pick up work from an exported handoff, run
`python scripts/moves.py unpack-handoff handoff.json --output-dir restored`.
It verifies the bundle before restoring the exact plan and every supplied
checkpoint into a new directory. Read `restored/resume-review.json` before
further work; earlier stops remain active. Follow the
[handoff recovery walkthrough](docs/resuming-handoffs.md), or run
`python examples/replay-handoff.py --output replay` for a complete synthetic
selection, handoff, recovery, checkpoint, and revision replay.

A successful command exit means a report was produced. Exit 0 does not mean an
experiment succeeded or was approved; 1 means invalid input or a file error,
and 2 means invalid command arguments. Read the outcome, warnings, and stop
reasons. Numeric success never overrides a stop condition or authorizes
continuation.

Selection fields do not establish who selected a move or approve execution.
Source URLs, dates, and high-stakes flags are declarations, not verified
support, freshness, or complete risk assessments. Lexical screening and schema
checks do not certify safety. Hashes and consistent handoffs bind content;
they do not authenticate its author, consent, approval, or observations.

## JSON compatibility

Both [v0.1](schemas/moves.schema.json) and [v0.2](schemas/moves-v0.2.schema.json)
remain supported. Both require five to seven moves, one `prioritized_action`,
and a `sources` array. Version 0.2 adds a selected move ID and measurable
experiment cards. The first choice in the recommendation must agree with the
selected ID; free-text meaning still needs human review.

Use v0.1 when meaningful numeric baselines are unknown, and identify what needs
measuring. Do not invent numbers to force v0.2. Version 0.2 retains a start bound
of 0 to 48 hours and duration of 1 to 48 hours. Test a narrow uncertainty within
that window rather than implying a long-term hypothesis has been proved.
The installed skill bundles both schemas and its strategy review reference.

## Integration notes

For concrete offline workflows using the bundled examples, see
[usage recipes](docs/usage-recipes.md); five copy-paste recipes cover v0.1
rendering, v0.2 selection and cards, the synthetic outcome replay,
cumulative checkpoint histories with CSV export, and the combined
constraint shortlist and source date audit. To choose between the two
schema versions using the actual required fields, the experiment card
bounds, and the CLI version gate, see the
[version decision tree](docs/version-decision.md). Both docs rely only on
files and commands that ship in this repository.

## Validate and package

From the repository root:

```sh
python scripts/validate.py
python scripts/validate_plan.py examples/example-plan.json
python scripts/validate_plan.py examples/bounded-plan.json --json
python scripts/moves.py outcome examples/bounded-plan.json examples/bounded-outcome.json
python -m unittest discover -s tests -v
python scripts/package.py --output dist
```

Use a fresh output directory for packaging. The builder uses only the standard
library and produces a versioned ZIP and SHA-256 checksum. Compare two clean
builds under the same environment to check reproducibility. Cross-platform
byte identity requires testing, not an assumption.

Extract the archive into a fresh directory, verify its checksum against the
builder's checksum file, then copy the extracted `skill/unconventional-moves`
directory to the project skill location above. A checksum detects a content
mismatch; it does not authenticate the publisher. Packaging does not publish
or change remote metadata.

Structural tests check contracts and workflow behavior. They do not prove
mechanism diversity or better decisions. See [behavioral evaluation](evals/README.md)
for the frozen rubric, optional model comparison, actual results, and limitations.
Ordinary tests remain offline.

## Important files

| File | Purpose |
| --- | --- |
| [SKILL.md](skill/unconventional-moves/SKILL.md) | Installable thinking instructions and output contract |
| [Strategy review](skill/unconventional-moves/references/strategy-review.md) | Causal diversity and experiment quality checks |
| [Invocation metadata](skill/unconventional-moves/agents/openai.yaml) | Display name, prompt, and implicit invocation policy |
| [Worksheet](templates/worksheet.md) | Copy-ready brief and move template |
| [Plan validator](scripts/validate_plan.py) | Structural validation and limited lexical screening |
| [Local CLI](scripts/moves.py) | Offline review and observation tracking |
| [Package builder](scripts/package.py) | Manifest-based archive and checksum |
| [Security](SECURITY.md) | Security scope and reporting guidance |
| [Contributing](CONTRIBUTING.md) | Contribution and verification rules |
| [Provenance](PROVENANCE.md) | Origin and independence disclosures |

Output quality still depends on the brief and the model. Novelty is contextual,
ranking is a judgment, and observations do not establish causation. The skill
does not verify private claims or replace qualified professional review.

EauDoon directed, reviewed, and takes responsibility for the result. This is an
independent community project, released under the [MIT License](LICENSE).
