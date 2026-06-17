# Quality Review: 5 Geneval-Retry SFT Trajectories

Input files reviewed:

- `data/smoke/geneval_diagnostics_5.jsonl`
- `data/processed/teacher_retry_actions_5.jsonl`
- `data/processed/geneval_retry_sft_5_full.jsonl`

## Summary Table

| index | prompt | failure type | expected skill | actual skill | full episode complete? | preserve/repair correct? | targeted retry? | verdict | notes |
|---:|---|---|---|---|---|---|---|---|---|
| 0 | three red apples on a blue plate | count_mismatch | quantity_counting | quantity_counting | yes | yes | yes | MINOR ISSUE | Correct retry logic. Mock retry judge marks counting passed but keeps first-attempt detector details with only two apples in user/tool context. |
| 1 | a green cube to the left of a yellow sphere | spatial_mismatch | spatial_layout | spatial_layout | yes | yes | yes | MINOR ISSUE | SFT normalized spatial fields are structured and non-empty. Source teacher action row still has stale empty spatial `failed_constraints`/`repair_targets`. Mock retry judge keeps first-attempt detector geometry. |
| 2 | two blue birds and one red car | color_mismatch | attribute_binding | attribute_binding | yes | yes | yes | MINOR ISSUE | Correctly repairs bird color while preserving count and red car. Mock retry judge marks color passed but keeps first-attempt detector detail containing a green bird. |
| 3 | a small dog under a wooden table | spatial_mismatch | spatial_layout | spatial_layout | yes | yes | yes | MINOR ISSUE | SFT normalized spatial fields are structured and non-empty. Source teacher action row still has stale empty spatial `failed_constraints`/`repair_targets`. Mock retry judge keeps first-attempt detector geometry. |
| 4 | four white flowers in a black vase | count_mismatch | quantity_counting | quantity_counting | yes | yes | yes | MINOR ISSUE | Correct count repair and preservation. Mock retry judge marks counting passed but keeps first-attempt detector details with three flowers. |

## Trajectory Reviews

### 0. Three Red Apples On A Blue Plate

Verdict: MINOR ISSUE

- Full episode structure: complete. The row includes parse constraints, first mock generation, first judge, diagnostic receipt, skill query, repair prompt, retry mock generation, retry mock judge, and submit.
- Failure typing: correct. The failed count maps to `count_mismatch`.
- Skill routing: correct. `count_mismatch` routes to `quantity_counting`.
- Preserve/repair separation: correct. It preserves apple redness and blue plate presence, and repairs exactly three apple instances.
- Targeted retry prompt: correct. The retry prompt explicitly asks for exactly three separate visible red apples on a blue plate.
- Regression awareness: present. It warns about changing colors and merging apples.
- Training mask quality: minor issue. Raw detector metadata appears in user/tool context, and the mock retry diagnostic keeps the first-attempt two-apple detection while marking counting as passed.
- Spatial normalization: not applicable.
- Sensitive content: no API key or credential observed.

### 1. Green Cube Left Of Yellow Sphere

Verdict: MINOR ISSUE

- Full episode structure: complete.
- Failure typing: correct. The spatial relation failure maps to `spatial_mismatch`.
- Skill routing: correct. `spatial_mismatch` routes to `spatial_layout`.
- Preserve/repair separation: correct. It preserves one cube, one sphere, cube green, and sphere yellow while repairing only left-right layout.
- Targeted retry prompt: correct. The retry prompt states exactly one green cube to the left of exactly one yellow sphere.
- Regression awareness: present. It warns about color changes and object count regressions.
- Training mask quality: minor issue. Raw detector metadata appears in user/tool context, and the mock retry diagnostic keeps first-attempt geometry while marking the spatial relation as passed.
- Spatial normalization: correct in `geneval_retry_sft_5_full.jsonl`; the row has a structured `spatial_relation` failed constraint and a `spatial_layout` repair target. Minor source issue: the corresponding row in `teacher_retry_actions_5.jsonl` still has stale empty normalized spatial fields.
- Sensitive content: no API key or credential observed.

### 2. Two Blue Birds And One Red Car

Verdict: MINOR ISSUE

- Full episode structure: complete.
- Failure typing: correct. The color binding failure maps to `color_mismatch`.
- Skill routing: correct. `color_mismatch` routes to `attribute_binding`.
- Preserve/repair separation: correct. It preserves two birds, one car, and red car, while repairing bird color only.
- Targeted retry prompt: correct. The retry prompt explicitly asks for both birds to be clearly blue with exactly two birds and one red car.
- Regression awareness: present. It warns about count regressions and red car color regression.
- Training mask quality: minor issue. Raw detector metadata appears in user/tool context, and the mock retry diagnostic keeps the original green-bird detection while marking color binding as passed.
- Spatial normalization: not applicable.
- Sensitive content: no API key or credential observed.

### 3. Small Dog Under Wooden Table

Verdict: MINOR ISSUE

- Full episode structure: complete.
- Failure typing: correct. The failed under-table relation maps to `spatial_mismatch`.
- Skill routing: correct. `spatial_mismatch` routes to `spatial_layout`.
- Preserve/repair separation: correct. It preserves one dog, one table, dog smallness, and table woodenness while repairing only the under-table layout.
- Targeted retry prompt: correct. The retry prompt asks for the dog clearly positioned under the table.
- Regression awareness: present. It warns about count regression and reduced visibility.
- Training mask quality: minor issue. Raw detector metadata appears in user/tool context, and the mock retry diagnostic keeps first-attempt geometry while marking the spatial relation as passed.
- Spatial normalization: correct in `geneval_retry_sft_5_full.jsonl`; the row has a structured `spatial_relation` failed constraint and a `spatial_layout` repair target. Minor source issue: the corresponding row in `teacher_retry_actions_5.jsonl` still has stale empty normalized spatial fields.
- Sensitive content: no API key or credential observed.

### 4. Four White Flowers In A Black Vase

Verdict: MINOR ISSUE

- Full episode structure: complete.
- Failure typing: correct. The failed flower count maps to `count_mismatch`.
- Skill routing: correct. `count_mismatch` routes to `quantity_counting`.
- Preserve/repair separation: correct. It preserves white flowers, black vase, one vase, and object presence while repairing exactly four flower instances.
- Targeted retry prompt: correct. The retry prompt asks for exactly four separate visible white flowers in one black vase.
- Regression awareness: present. It warns about color regression and merged/obscured flower instances.
- Training mask quality: minor issue. Raw detector metadata appears in user/tool context, and the mock retry diagnostic keeps first-attempt three-flower detections while marking counting as passed.
- Spatial normalization: not applicable.
- Sensitive content: no API key or credential observed.

## Overall Verdict

Ready to scale to 50: no.

The five trajectories are semantically aligned and structurally complete, and the automatic critical checks pass. However, there is a repeated data-quality issue: mock retry diagnostics mark checks as passed while retaining first-attempt raw detector details that still show the original failure. The rows also include raw detector metadata and generated image ids in user/tool context. This is acceptable only if the downstream SFT pipeline masks user/tool observations and the model is trained only on assistant actions; that masking contract is not recorded in these rows.

## Required Fixes Before Scaling

- Sanitize mock retry judge observations before scaling: either remove `detected` arrays, bounding boxes, scores, and generated image ids from training contexts, or synthesize internally consistent improved diagnostics.
- Add an explicit masking contract or dataset field if the downstream SFT loader needs to distinguish assistant-loss tokens from user/tool observation tokens.
- Regenerate teacher action files, or rely only on recomputed SFT normalization, so spatial source rows do not retain stale empty `normalized_diagnostic.failed_constraints` and `repair_targets`.

## Optional Improvements

- Add an explicit `diagnose_failed_constraints` step between diagnostic receipt and `query_skill`; the current `receive_geneval_diagnostic` step contains the diagnosis, but a separate step would make the training signal clearer.
- Store compact tool observations with only `checks`, `failure_reason`, and normalized failures instead of full detector output.
- Add a checker mode that fails on contradictory mock improved diagnostics once the sanitized format is implemented.

## Data Hygiene Addendum

Status after hygiene fix: ready to scale to 50.

The SFT exporter now separates `assistant_trainable_messages`, `tool_observations`, `raw_detector_outputs`, and `non_trainable_context`. It also emits `masking_metadata` that directs downstream exporters to train only assistant diagnostic summaries, assistant tool calls, assistant repair prompts, assistant retry decisions, and assistant submit/discard decisions.

The regenerated `data/processed/geneval_retry_sft_5_full.jsonl` uses compact diagnostics in SFT-facing contexts by default. Raw detector outputs remain available only in `raw_detector_outputs`, which is explicitly marked non-trainable. The quality checker now reports 0 critical issues and 0 warnings on the regenerated file.
