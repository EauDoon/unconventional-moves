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
