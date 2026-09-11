# Contributing

Keep contributions narrow, original, and consistent with the project's safety
and evidence boundaries.

## Content requirements

- Keep the installable skill concise, imperative, and useful without the CLI.
- For a normal completed plan, give five to seven feasible, mechanism-distinct
  moves. Explain limitations or refuse unsafe goals without padding.
- Separate desired outcome from assumed method, identify the likely bottleneck,
  and compare the conventional baseline outside the move count.
- Explain each concrete action, why it could work here, and its failure condition.
- Make every reversible test startable within 48 hours and capable of changing a
  decision. Include a hypothesis, observation, success signal, stop, bounds, and
  rollback in existing fields. Preserve versioned duration constraints.
- Distinguish supplied facts, checked facts, inference, and speculation. Do not
  invent measurements to satisfy v0.2; use v0.1 when meaningful inputs are unknown.
- Require current reliable evidence for high-stakes claims; when unavailable,
  limit advice to source gathering or non-consequential steps.
- Reject illegal, deceptive, reckless, exploitative, or unsafe actions. Preserve
  consent and affected parties' interests without repetitive low-risk boilerplate.
- Put Sources before the one final prioritized action in prose. Explain that
  choice against the strongest alternative and name its first concrete step.
- Use fictional examples across partnership activation, product adoption,
  distribution, operational efficiency, and personal learning. Clearly label
  synthetic numeric values and observations. Do not invent real company results.
- Do not add personal details, employer or client content, local paths, account
  identifiers, credentials, external assets, runtime dependencies, or copied
  third-party content. Do not use em dashes in public files.

## Contribution workflow

1. Reproduce the problem and explain the smallest coherent behavior change.
2. Freeze a rubric before tuning behavioral instructions. Keep held-out cases
   separate from tuning. Structural tests do not establish semantic improvement.
3. Add regression coverage for confirmed defects, then implement the fix.
4. Run `python scripts/validate.py`, both example plan validators, and
   `python -m unittest discover -s tests -v`. Use a verified Python interpreter.
5. Build twice in fresh directories, compare checksums in the same environment,
   and exercise the extracted package away from the checkout.
6. Review the diff, trust claims, compatibility, links, privacy, punctuation, and
   unexpected files. Update bundled references and the package manifest together.
7. Record actual commands, results, environments, and limitations. Optional
   model evaluations must record prompts, runtime, outputs, and independent
   review where available. Report unexecuted behavioral comparisons as NOT RUN.

Product direction, evaluation, review, and acceptance remain with EauDoon.
Contributors must disclose material third-party provenance and licensing
obligations. Checks, hashes, source declarations, and selection fields do not
certify safety, authenticate observations, or approve execution.
