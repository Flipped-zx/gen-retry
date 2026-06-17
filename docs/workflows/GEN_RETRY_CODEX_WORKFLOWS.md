# Gen-Retry Codex Workflows

This file defines reusable workflows for developing Gen-Retry with Codex.

## Workflow 1: Repo Digest

Use when introducing external repositories.

Steps:
1. Read AGENTS.md.
2. Treat external repositories as read-only.
3. Identify key files and data formats.
4. Extract tool protocols, trajectory formats, training scripts, and evaluation interfaces.
5. Write persistent digest under docs/repo_digests/.
6. Update docs/CODEBASE_MAP.md.
7. Do not copy code blindly.

Success criteria:
- Digest explains what to reuse, what to avoid, and how it informs Gen-Retry.
- Future Codex sessions can read the digest instead of rescanning the source repo.

## Workflow 2: Safe Skeleton

Use when creating a new module.

Steps:
1. Create package structure.
2. Add schemas/configs/examples first.
3. Implement stdlib-safe code where possible.
4. Do not install dependencies.
5. Run python3 scripts/safe_check.py.
6. Update docs/PROGRESS.md and docs/CODEX_HANDOFF.md.

Success criteria:
- No environment modification.
- All files are inside gen-retry.
- safe_check passes.

## Workflow 3: Schema-First Development

Use when adding data or API logic.

Steps:
1. Define input schema.
2. Define output schema.
3. Add valid example.
4. Add invalid example if useful.
5. Implement converter/builder.
6. Validate examples.

Success criteria:
- Data format is explicit.
- Errors are understandable.
- Downstream scripts can rely on stable fields.

## Workflow 4: Mock-First Pipeline

Use when adding API, generation, evaluator, or training pipeline.

Steps:
1. Implement mock mode first.
2. Implement dry-run CLI.
3. Require explicit flag for real external calls.
4. Do not call real API in tests.
5. Document exact command for real usage.

Success criteria:
- Pipeline can run locally without API keys or installed ML dependencies.
- Real mode is opt-in.

## Workflow 5: Teacher Retry Action Builder

Use when converting Geneval diagnostics to retry actions.

Input:
- prompt
- expected constraints
- detected objects
- checks
- failure_reason
- skill library

Output:
- decision
- failure_types
- skills_to_call
- preserve_constraints
- repair_constraints
- repair_strategy
- retry_prompt
- expected_improvement
- regression_risks

Rules:
- Do not produce generic prompt rewriting.
- Always separate preserve and repair.
- Always align skills_to_call with failure_types.
- Counting failure should route to quantity_counting.
- Color/attribute failure should route to attribute_binding.
- Spatial failure should route to spatial_layout.
- Object missing should route to object_presence.
- Occlusion/low visibility should route to visibility_and_anti_occlusion.

## Workflow 6: SFT Trajectory Builder

Use when constructing training data.

Trajectory shape:
prompt
→ parse constraints
→ first generation
→ judge diagnostic
→ diagnose failure
→ query skill
→ repair prompt
→ retry generation
→ rejudge
→ submit/discard

Train on:
- assistant diagnostic summaries
- assistant tool calls
- assistant retry decisions
- assistant repair prompt
- assistant submit decision

Do not train on:
- tool observations
- detector outputs
- generated image metadata
- raw judge outputs

Success criteria:
- The trajectory teaches diagnostic-conditioned retry.
- Failed constraints are repaired.
- Previously passed constraints are preserved.

## Workflow 7: Evaluation Metrics

Use when evaluating retry.

Metrics:
- final Geneval pass rate
- retry success rate
- failed-constraint repair rate
- regression rate
- improvement per generation budget
- skill routing accuracy
- action-diagnostic alignment

Baselines:
- single generation
- best-of-N
- blind retry
- natural-language critique retry
- structured diagnostic retry

## Workflow 8: Handoff and Checkpoint

At the end of every Codex session:
1. Update docs/PROGRESS.md.
2. Update docs/CODEX_HANDOFF.md.
3. List changed files.
4. List validation commands and results.
5. List blockers.
6. List next recommended step.
7. Do not leave hidden state only in chat.

