# Gen-Retry RL Roadmap

This is a design-only roadmap. Do not implement or run RL training until SFT data quality, exporters, and pilot evaluations are stable.

## What To Borrow From GenEvolve

GenEvolve is useful as a trajectory-optimization reference:

- tool-orchestrated trajectory formulation;
- explicit skill or knowledge-query mechanism, similar to `query_knowledge`;
- SFT cold start before RL;
- visual experience reuse and best-worst comparisons;
- GRPO-style trajectory optimization over multi-step agent behavior.

For Gen-Retry, the analogous tool step is `query_skill`, and the trajectory is centered on repairing a failed image-generation attempt rather than optimizing a first-pass generation plan.

## What To Borrow From Gen-Searcher

Gen-Searcher is useful for grounded search-style trajectories:

- `search`, `image_search`, and `browse` style action sequences;
- separate text and image reward signals;
- grounded prompt evaluation;
- multi-step information gathering before a final answer.

For Gen-Retry, similar structure can support skill lookup, diagnostic interpretation, and grounded prompt repair. The reward should be tied to retry improvement, not generic search success.

## How Gen-Retry Differs

Gen-Retry starts after a failed generation attempt. The central input is diagnostic feedback:

```text
prompt + generation history + Geneval diagnostic -> repair action
```

The agent must balance two objectives:

- repair failed constraints;
- preserve already-passed constraints.

This differs from first-pass image generation because changing the prompt can improve one constraint while regressing another. The reward must therefore penalize regressions, not only reward newly satisfied checks.

## Future RL Formulation

State:

```text
source prompt
+ previous generation and retry history
+ normalized Geneval diagnostic
+ passed constraints
+ failed constraints
+ available retry skills
```

Action:

```text
query_skill(skill_name)
repair_prompt(text)
retry_generation(prompt)
submit
discard
```

Reward:

```text
repaired failed constraints
- regressed passed constraints
- retry cost
- invalid action penalty
- ungrounded prompt drift penalty
```

Useful reward components:

- count of failed constraints fixed after retry;
- count of previously passed constraints still passing;
- skill/failure alignment;
- targeted repair prompt score;
- penalty for adding unsupported objects, colors, counts, or spatial relations;
- penalty for repeated retries without improvement.

## Preserve-Versus-Repair Reward

A retry that fixes a missing object but breaks a correct color binding should not receive full credit. A practical reward should compute:

```text
improvement = fixed_failed_checks - regressed_passed_checks
```

For mixed failures, reward should be per-constraint rather than all-or-nothing. This allows the policy to learn that targeted, minimal edits are better than broad prompt rewrites.

## Future RL File Plan

Do not create these files until the RL phase begins:

- `src/gen_retry/rl/rewards.py`
- `src/gen_retry/rl/rollout.py`
- `src/gen_retry/rl/grpo_adapter.py`
- `configs/train/rl_retry_grpo.yaml`

Planned roles:

- `rewards.py`: compute preserve/repair rewards from before/after diagnostics.
- `rollout.py`: execute retry trajectories in a controlled environment.
- `grpo_adapter.py`: connect trajectory batches to a GRPO trainer.
- `rl_retry_grpo.yaml`: record model, LoRA, rollout, reward, and logging settings.

## Recommended Sequence

1. Finish SFT row building and masking.
2. Export clean Qwen-compatible data.
3. Run 500/1k LoRA pilot training.
4. Evaluate retry behavior on held-out Geneval diagnostics.
5. Design offline reward checks using existing diagnostics.
6. Only then implement rollout and GRPO integration.

RL should remain design-only until the SFT student can already perform failure typing, skill routing, targeted repair, and submit/discard decisions with reasonable consistency.
