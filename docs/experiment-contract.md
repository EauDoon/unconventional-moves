# Bounded experiment contract

Version 0.1 plans remain valid and unchanged. Version 0.2 adds one `selected_move_id` and a required `experiment` object on each move. See the [schema](../schemas/moves-v0.2.schema.json).

The experiment declares a hypothesis, metric, numeric baseline and target, improvement direction, start delay of 0 to 48 whole hours, duration of 1 to 48 whole hours, maximum active minutes, exposure, and rollback. The target must improve on baseline in the stated direction. Active minutes cannot exceed the experiment duration. These checks supplement JSON Schema, which does not enforce cross-field comparisons or unique move IDs.

Numbers are declared expectations, never evidence of a real result. `consenting_participants` records intended exposure; it does not establish consent. A human must verify consent, realistic bounds, safety, source relevance, and alignment between the selected move and the prioritized action. Validation does not certify any of these.

Targets and observations are compared using decimal representations of the parsed
numeric values, consistent with progress calculations and cumulative time checks.
Standard JSON float parsing does not preserve arbitrary decimal precision. Older generated handoffs
that depended on a mixed float/integer comparison edge case may need their
reports regenerated from the original plan and observations. No observation
should be rewritten to make a report match.

Lexical validation recognizes narrow direct prevention clauses such as
`Do not steal credentials` and `Stop if harassment occurs`, while checking each
harmful match and coordinated clause separately. It does not exempt a whole
sentence merely because it contains negation, and conditional exceptions remain flagged. Ambiguous wording can still be
rejected; clarify the proposed action instead of treating a pass as safety proof.
Quotation, context, obfuscation, intent, and completeness require semantic review.
The repository text scan is also only a lexical check, not behavioral evaluation.

The `high_stakes` flag and every source record are caller declarations. URL syntax,
a nonempty source list, and a supplied date do not verify authority, freshness,
claim support, or whether the caller classified the risk correctly. A false flag
must not be read as a low-risk certification. The offline CLI cannot check sources.
