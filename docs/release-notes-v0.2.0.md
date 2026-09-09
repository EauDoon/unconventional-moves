# Version 0.2.0

The skill now includes a local authoring and experiment-review workbook. Existing version 0.1 plans still validate. Version 0.2 plans add an explicit selected move and measured-target declarations, bounded time, exposure, and rollback. The Python tools prepare and review artifacts; they never execute the moves.

The runnable synthetic language-practice workflow is in the [README](../README.md). Full field guidance is in the [local workflow](local-workflow.md). A successful numeric target is reported separately from stop decisions. Unknown observations stay unknown. Changed plan revisions require new outcome records.

The installed skill contains its own schema references. Repository checks enforce identical bytes between bundled and canonical schemas. Package tests build the ZIP, verify its checksum, extract it, invoke tools from the extracted directory, and copy the skill into a temporary synthetic project to verify its local links. They do not modify a real installation.

Limitations: deterministic text review cannot establish novelty, causation, source currency, legal authority, consent, safety, or real-world effectiveness. No empirical superiority is claimed. Numeric bounds are author declarations and require human judgment. This release has no hosted UI or deployment component.
