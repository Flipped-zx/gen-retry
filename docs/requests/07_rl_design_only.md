# Request 07: RL Design Only

Goal: continue RL design without implementing or running RL training.

Use `docs/RL_ROADMAP.md` as the starting point.

## Constraints

- Do not run training.
- Do not run RL.
- Do not call image generators.
- Do not call the real teacher API unless explicitly requested.
- Do not install dependencies.
- Do not create RL source files until the user approves implementation.

## Design Questions

1. What exact state representation should Gen-Retry expose?
2. Which actions should be available during rollout?
3. How should preserve-vs-repair reward be computed?
4. How should retry cost be penalized?
5. How should failed constraints and regressed passed constraints be weighted?
6. How should invalid tool calls or ungrounded prompt drift be penalized?
7. What offline diagnostics can approximate rewards before real image generation is available?

## Expected Output

- A refined RL design document.
- Reward formulas.
- Rollout interface sketch.
- Risks and prerequisites.
- A list of files to implement later, without creating them yet.

Future files, only after approval:

- `src/gen_retry/rl/rewards.py`
- `src/gen_retry/rl/rollout.py`
- `src/gen_retry/rl/grpo_adapter.py`
- `configs/train/rl_retry_grpo.yaml`
