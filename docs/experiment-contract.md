# Bounded experiment contract

Version 0.1 plans remain valid and unchanged. Version 0.2 adds one `selected_move_id` and a required `experiment` object on each move. See the [schema](../schemas/moves-v0.2.schema.json).

The experiment declares a hypothesis, metric, numeric baseline and target, improvement direction, start delay of 0 to 48 whole hours, duration of 1 to 48 whole hours, maximum active minutes, exposure, and rollback. The target must improve on baseline in the stated direction. Active minutes cannot exceed the experiment duration. These checks supplement JSON Schema, which does not enforce cross-field comparisons or unique move IDs.

Numbers are declared expectations, never evidence of a real result. `consenting_participants` records intended exposure; it does not establish consent. A human must verify consent, realistic bounds, safety, source relevance, and alignment between the selected move and the prioritized action. Validation does not certify any of these.
