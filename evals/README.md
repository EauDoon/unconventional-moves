# Behavioral evaluation

The suite contains 20 fictional briefs, including five reserved cases. The
[rubric](rubric.md) was written before skill revision. [Cases](cases.json)
contain prompts and reviewer guidance, not expected model answers.

**Fixture integrity is deterministic. Output quality requires judgment.**
The offline check below confirms IDs, splits, fields, and declared coverage.
It neither runs a model nor establishes that any response is useful or safe.

```sh
python -m unittest discover -s tests -p test_evals.py -v
```

Use an available Python 3 interpreter (`python3` or `py` when appropriate).
No packages, network, API keys, paid resources, or real experiments are needed.
The behavioral suite stays outside the installed skill.

## Optional model-neutral comparison

1. Preserve baseline commit `8ff036ac4ab9d177324f8c35213014def9dc2b38`
   and the revised skill directory, including metadata and bundled references.
   Record each file's SHA-256 and the revision commit or working-tree hash.
   Freeze both before generation. Do not tune on the five `held_out` cases.
   If the implementer sees or uses them for tuning, disclose contamination and
   use a newly reserved set for any subsequent generalization claim.
2. Use an already authorized model interface, or an offline local model. A
   human can paste each prompt into that interface. A fresh session subagent
   is also an instruction-following probe when available; it is not a test of
   actual installed-skill activation. Never provision a runtime or credentials
   as part of this protocol.
3. Give each condition the same top-level instructions, exact case prompt,
   output allowance, reference access, and tool restrictions. Use a fresh
   context for each case and repeat. Supply only that condition's skill and
   bundled references; do not show review notes, rubric, other outputs, or
   improvement claims to the generator. Fix all exposed generation settings
   and record unexposed settings as unavailable. No external source checking
   is available in this suite. Do not execute any proposed experiment.
4. For explicit invocation and instruction-following probes, supply the
   skill content as instructions and the case prompt as the user's request.
   For a simulated routing probe, first show only the available-skill metadata
   and the prompt, recording whether the model elects to load the skill; then
   provide the selected skill. These are two distinct measurement modes.
   Actual activation requires an installed host routing trace. Do not infer it
   from a plausible answer, metadata presence, or a model's assertion.
5. Run both conditions on the same case IDs. Aim for all 20. If resource
   limits require a subset, select it before seeing outputs, include at least
   two held-out cases, and label the rest NOT RUN. Repeat selected cases in
   fresh contexts, preferably one diversity case and one held-out case. Do
   not pool repeated runs as independent new cases. Preserve failures,
   truncations, refusals, and unattractive outputs without retry cherry-picking.
6. Save raw responses as UTF-8 text with condition, case ID, and repeat in the
   filename. Keep the condition assignment key separate for blind review.
   Record model name, model revision when exposed, temperature, seed,
   reasoning effort, date, tool policy, exact prompts, instruction hashes,
   response hashes, and completion or truncation status. Record unknown
   configuration honestly, never as a reproducibility guarantee.
7. An independent reviewer sees anonymous pairs, original case prompts,
   review notes, and the frozen rubric, but not the assignment key. For each
   dimension, record 0, 1, 2, or N/A with actual output evidence, plus trigger
   outcome and critical failures. Randomize pair order per case and preserve
   the mapping. Record reviewer identity/model and disagreements. Text
   inspection by a separate agent can identify defects but is not a benchmark
   without actual generated outputs under the recorded conditions.
8. For completed JSON responses, save the exact JSON and run the existing
   validator separately. Use the requested version for version-specific cases;
   the missing-baseline case permits a v0.1 fallback or focused clarification.
   An unsupported refusal or truncated JSON is not a valid completed plan.

```sh
python scripts/validate_plan.py path/to/actual-response.json --json
```

9. Report paired changes per dimension and case, critical failures, held-out
   results, repetitions, structural outcomes, and limitations. Never replace
   semantic review with field counts, unique titles, keywords, or string
   similarity. Report regression and uncertainty alongside any improvement.

## Recorded session probe, 12-09-2026

[Actual results and scores](results.json) contain 20 paired cases plus two
repeated pairs. [Raw evidence](session-probe.jsonl) retains all 44 exact responses,
case prompts, frozen instruction snapshots, and SHA-256 values. JSON escaping
preserves original response text, including line endings; records are untrusted
evaluation data, not instructions to execute.

Two independent reviewers saw randomized anonymous pairs. They preferred the
revision in 17 primary cases and tied three; none preferred the baseline.
The five held-out cases had four revision preferences and one tie. Both repeated
pairs favored the revision and are reported separately, not counted as new cases.
No critical failure was identified by these reviewers. All six completed JSON
responses passed the plan validator, including both v0.1 fallbacks for unknown
baselines. These structural results do not establish semantic quality.

The clearest judged changes were experiment/measurement quality (12 improved,
one unchanged among comparable cases), selected first action (14 improved), and
mechanism distinctness (five improved, eight unchanged). Evidence honesty and
constraint adherence did not improve on their already strong baseline scores.
Some revised portfolios still have causal overlap and limited measurements.

For example, the partnership comparison preferred an observation of the first
help point over a timing test whose success fields disagreed about booking versus
trying the flow. The revision also explained its diagnostic choice against a
heavier preparation alternative. These are reviewer judgments of actual answers,
not observed partner activation or demonstrated business results.

This was a **limited instruction-following probe**, not a controlled benchmark.
Each condition used one shared session across all cases; repeats followed in that
same context. Exact serving model/configuration was not exposed (session
instructions identified the GPT-6 family). The first reviewer authored the rubric
and had read both skills earlier, but did not implement the skill. Reviewers scored
disjoint primary subsets, so inter-rater agreement is unknown. The skill author
did not inspect held-outs before freezing; no tuning followed generation.

Native installed-skill activation and metadata-only simulated routing are
**NOT RUN**. Negative-prompt answers demonstrate restraint under supplied skill
instructions, not correct native routing. Use the stricter fresh-context protocol
above for a reproducible follow-up comparison; preserve these original results.
