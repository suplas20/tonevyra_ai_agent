# Prompt — Add Loop Engineering Support

Read `AGENTS.md` first. Then read:

- `skills/loop-engineering/SKILL.md`
- `skills/testing-harness/SKILL.md`
- `skills/agent-worker-pipeline/SKILL.md`
- `harness/CONTRACT.md`

Implement loop evidence for the product agent. Loop Engineering means bounded autonomous control with durable evidence, not a new UI or simulated environment.

Requirements:

- Add loop_name and loop_iteration evidence to task events.
- Use allowed loop names only.
- Ensure Processing Loop and Quality Loop terminate in final task status.
- Do not create infinite retry loops.
- Update or add harness support so `verify_loop_events.py` can pass.
- Do not connect real Qwen or real Lightroom for this task.
