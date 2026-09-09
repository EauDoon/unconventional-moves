---
name: unconventional-moves
description: "Generate five to seven practical, non-obvious approaches to a supplied goal, each with a concrete move, an overlooked reason, and a reversible 48-hour test. Use when a user wants unconventional options, fresh approaches beyond standard advice, varied problem-solving mechanisms, or one prioritized low-risk experiment."
---

# Unconventional Moves

## Build the response

1. Frame the goal, desired outcome, constraints, non-negotiables, and time horizon. Ask one focused question only when a missing detail materially changes safety or usefulness. Otherwise state necessary assumptions.
2. Generate five to seven genuinely distinct approaches. Draw from different mechanisms such as inversion, subtraction, incentive changes, constraint removal, neglected stakeholders, timing, precommitment, and asymmetric experiments. Do not force an irrelevant mechanism or disguise standard advice as novelty. The final count must be between five and seven.
3. Screen every approach for legality, honesty, reversibility, downside, and exposure to other people. Reject illegal, deceptive, reckless, exploitative, or unsafe approaches. Briefly explain the boundary and redirect to a safer lawful alternative when possible.
4. Separate what is known from what is inferred. Label unsupported possibilities as speculation. Never claim personal experience, access to private data, or inspection of training data.
5. Rank the valid approaches by likely learning value, reversibility, cost, and fit with the stated constraints. End with exactly one prioritized action, not a tie or a list of next steps.

## Use this output shape

For each idea, provide:

### Idea N: Title (mechanism)

- **Concrete move:** State the action precisely.
- **Why overlooked:** Identify the assumption, incentive, habit, stakeholder, constraint, or timing effect that hides it.
- **48-hour test:** Define a tiny reversible test that can begin within 48 hours. Include a success signal and a stop condition.
- **Success signal:** State the observable result that would justify continuing the test.
- **Stop condition:** State the result, risk, or time boundary that ends the test.
- **Evidence status:** Separate prompt-supported or source-supported facts from inference and speculation. Do not invent a fact to fill a category.
- **Bounds:** State the limit on time, cost, exposure, or commitment when material.
- **Sources:** For high-stakes output, list current reliable sources and what each source supports. Write `Sources: none required` only when the goal is not high stakes.

After all ideas, provide:

**Prioritized action:** Select one idea, explain briefly why it should go first, and name its first concrete step.

The `Prioritized action` line must occur exactly once and name one action.

## Machine-readable mode

When JSON is requested, use the bundled [version 0.1 schema](references/moves.schema.json) for the original prose-based contract, or the [version 0.2 schema](references/moves-v0.2.schema.json) when the user wants measurable experiment cards. Both require five to seven moves, one prioritized action, and sources. Version 0.2 also requires one selected move ID and explicit numeric targets, time bounds, exposure, and rollback for each move. Declare unknown baselines as assumptions only when appropriate; do not invent measurements. If meaningful numbers cannot be supplied, keep version 0.1 and explain what needs measuring.

The full repository package includes optional local authoring, review, rendering, comparison, and outcome tools. These are not required to invoke the installed skill. Treat their checks as structural support. Before a trial, verify actual consent, realistic bounds, evidence, and rollback. Afterward, distinguish observation from causation, stop when a bound or stop condition is reached, and request fresh authority for consequential expansion. A successful target does not authorize continuation.

## Handle high-stakes goals

Treat goals involving health, safety, law, finance, or other consequential decisions as high stakes.

- Obtain and cite current reliable sources before making material factual claims.
- Prefer authoritative primary sources where available.
- If current reliable sources are unavailable, say that verification is incomplete and limit the response to source gathering or other non-consequential steps.
- End high-stakes output with a `## Sources` section listing each source title,
  publisher, date when available, URL, and the claim or boundary it supports.
- Keep experiments small, reversible, and bounded by explicit stop conditions.
- Minimize downside and third-party exposure.
- Recommend qualified professional review when the decision exceeds safe general guidance.

Do not let novelty override evidence, consent, legality, or safety.

## Sources

For a high-stakes response, list current reliable sources here, with title,
publisher, date when available, URL, and the claim or boundary each source
supports. If no current reliable source can be checked, write `Verification
incomplete` and limit the response to source gathering or a non-consequential
experiment.
