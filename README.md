# Unconventional Moves

Unconventional Moves is a small, dependency-free Codex skill that turns a supplied goal into five to seven practical, non-obvious approaches. Each approach includes a concrete move, why it is often overlooked, and a tiny reversible test that can begin within 48 hours.

## Purpose

Use the skill when standard advice feels exhausted or when a goal would benefit from a different mechanism. It deliberately varies mechanisms such as inversion, subtraction, incentive changes, constraint removal, neglected stakeholders, timing, precommitment, and asymmetric experiments. It ends with one prioritized action so ideation leads to a bounded next step.

## Epistemic boundaries

The skill treats ideas as hypotheses, not established truths. It separates:

- facts supported by the prompt or current reliable sources;
- inferences drawn from those facts; and
- speculation that still needs testing.

It must not claim personal experience, access to private data, or inspection of training data. For high-stakes goals, it requires current reliable sources, uses bounded experiments with explicit stop conditions, and avoids presenting general ideation as professional advice. If current evidence is unavailable, the response must say so and limit the recommendation accordingly.

## Safety boundaries

The skill rejects illegal, deceptive, reckless, exploitative, and unsafe ideas. It redirects toward a lawful and safer version of the goal when possible. High-stakes suggestions must minimize exposure, remain reversible where practical, and identify when qualified professional review is needed.

## Installation

Copy the `skill/unconventional-moves` directory into `.agents/skills/unconventional-moves` in the project where you want to use it. No external dependencies or assets are required.

Invoke it explicitly with `$unconventional-moves`, or let Codex invoke it when a request clearly calls for practical unconventional approaches.

## Repository layout

```text
.
|-- README.md
|-- LICENSE
|-- SECURITY.md
|-- CONTRIBUTING.md
|-- PROVENANCE.md
|-- examples/
|   `-- example-prompts.md
`-- skill/
    `-- unconventional-moves/
        |-- SKILL.md
        `-- agents/
            `-- openai.yaml
```

## Synthetic examples

These examples are fictional and contain no real person, organization, or product information.

### Learning a language

> Use $unconventional-moves to generate six practical, non-obvious ways a fictional beginner could make language practice consistent during an irregular week. Include a reversible test that can begin within 48 hours for every idea.

### Reducing meeting overload

> Use $unconventional-moves to suggest five safe experiments a fictional team could use to reduce meeting overload without losing essential decisions or accountability. End with one prioritized action.

### Validating a small product idea

> Use $unconventional-moves to generate seven low-cost, reversible ways a fictional maker could validate a small product idea before building it. Separate facts, inferences, and speculation.

More ready-to-use versions are in `examples/example-prompts.md`.

## Limitations

- Results depend on the clarity and accuracy of the supplied goal and constraints.
- Novelty is contextual. An idea that is unusual in one setting may be routine in another.
- A 48-hour test can reduce uncertainty but cannot prove long-term success.
- The skill does not execute actions, verify private claims, or replace current authoritative sources.
- Unsafe goals may be refused instead of receiving five to seven approaches.

## Independence and authorship

This is an independent community project. It is not an OpenAI product, and OpenAI does not endorse it.

Project direction and requirements are by Oonyl. This public package was drafted and tested with OpenAI Codex. Final evaluation, review, and acceptance remain with Oonyl.

## License

Released under the MIT License. See `LICENSE`.
