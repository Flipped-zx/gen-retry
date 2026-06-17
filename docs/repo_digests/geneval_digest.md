# GenEval Digest

Source inspected read-only from `../GenEval`.

## Key Tree

```text
../GenEval/
  README.md
  environment.yml
  prompts/
    create_prompts.py
    evaluation_metadata.jsonl
    generation_prompts.txt
    object_names.txt
  evaluation/
    evaluate_images.py
    summary_scores.py
    object_names.txt
    download_models.sh
  generation/
    diffusers_generate.py
  annotations/
    annotations_*.csv
```

## Prompt Categories

`prompts/create_prompts.py` builds six task tags:

- `single_object`
- `two_object`
- `counting`
- `colors`
- `position`
- `color_attr`

Each metadata row contains a natural-language `prompt`, a `tag`, and one or more `include` clauses. Some categories also include `exclude` clauses. Examples:

```json
{"tag": "single_object", "include": [{"class": "bench", "count": 1}], "prompt": "a photo of a bench"}
```

Counting prompts include an `exclude` clause for count + 1. Color prompts add `color`. Position prompts add `position: [relation, target_group_index]`.

## Evaluator Interface

`evaluation/evaluate_images.py` is invoked as:

```bash
python evaluation/evaluate_images.py \
  "<IMAGE_FOLDER>" \
  --outfile "<RESULTS_FOLDER>/results.jsonl" \
  --model-path "<OBJECT_DETECTOR_FOLDER>"
```

Expected generated image layout:

```text
<IMAGE_FOLDER>/
  00000/
    metadata.jsonl
    samples/
      0000.png
      0001.png
      ...
```

The evaluator loads each folder's `metadata.jsonl`, runs detector inference for each sample image, and writes a JSONL result with:

- `filename`
- `tag`
- `prompt`
- `correct`
- `reason`
- `metadata` as a serialized JSON string
- `details` as a serialized JSON object of detected boxes by class

The public script asserts CUDA availability and imports `mmdet`, `open_clip`, `torch`, `pandas`, and `PIL`. Gen-Retry Stage 2 does not run this evaluator locally.

## Intermediate Detection Outputs

`evaluate_image()` constructs a `detected` mapping:

```python
{
  "apple": [(bbox, mask), ...],
  "plate": [(bbox, mask), ...]
}
```

It then serializes only the boxes into `details`:

```json
{
  "apple": [[x1, y1, x2, y2, score], ...]
}
```

For a Gen-Retry diagnostic normalizer, the useful fields are:

- `metadata`: expected constraints.
- `details`: detected object boxes.
- `correct`: aggregate pass/fail.
- `reason`: concise failure explanation, for example missing count or color mismatch.

The Stage 2 example uses a friendlier normalized diagnostic shape with `expected`, `detected`, and `checks`, but it should remain convertible from these GenEval result rows.

## Object, Count, Color, And Spatial Checks

`evaluate()` applies checks over `metadata["include"]` and `metadata["exclude"]`.

Object/count:

- For each include requirement, it reads `classname` and `count`.
- It takes the top detected objects for that class.
- If fewer than required are found, it marks incorrect and adds a reason like `expected apple>=3, found 2`.

Color:

- If an include clause has `color`, it crops or masks detected objects and classifies color with CLIP zero-shot prompts.
- It requires enough objects of the expected color.
- Failure reasons report expected color count and observed color counts.

Spatial:

- If an include clause has `position`, it compares each object against a previously matched target group.
- `relative_position()` computes left/right/above/below after a threshold based on object dimensions.
- It records reasons when the expected relation is missing.

Exclude:

- For each exclude requirement, it fails if detected count is greater than or equal to the forbidden threshold.

Detection thresholds:

- normal threshold defaults to `0.3`
- counting threshold defaults to `0.9`
- max objects defaults to `16`
- non-max overlap and position threshold are configurable through `--options`

## Pass/Fail Aggregation

`summary_scores.py` reads the evaluator JSONL and prints:

- total images
- total prompts
- percent correct images
- percent correct prompts, using any correct image for a metadata group
- per-tag accuracy
- overall score as average over task tag accuracies

For retry training, per-image correctness is useful for step-level diagnostics, while per-prompt any-pass can be used later for candidate selection.

## Accessing Per-Prompt Diagnostics

The smallest useful per-prompt diagnostic can be derived from each JSONL row:

```json
{
  "prompt": "...",
  "category": "<tag>",
  "expected": "<parse metadata include/exclude>",
  "detected": "<parse details>",
  "checks": {
    "object_presence": true,
    "counting": false,
    "color_binding": true
  },
  "failure_reason": "<reason>"
}
```

GenEval itself does not output separate named checks. Gen-Retry should infer check names from:

- `tag`
- expected metadata fields (`count`, `color`, `position`, `exclude`)
- the failure `reason`
- parsed detection `details`

The Stage 2 normalizer accepts this friendlier inferred diagnostic format so future Stage 3 code can adapt raw GenEval rows into retry trajectories.
