# Prompt — Add Feedback Learning Readiness

Read `AGENTS.md` first. Then read:

- `skills/feedback-learning/SKILL.md`
- `skills/lightroom-bridge/SKILL.md`
- `skills/correction-planning/SKILL.md`
- `skills/loop-engineering/SKILL.md`
- `harness/CONTRACT.md`

Add local feedback-learning readiness.

Requirements:

- Store AI-applied Lightroom Develop Settings snapshot when available.
- Support later sync of current/final Lightroom Develop Settings.
- Compute manual edit delta when current/final settings differ from AI-applied settings.
- Store explicit user feedback and reason tags locally.
- Create learning_samples / training_sample_manifest only when feedback is explicitly approved for learning.
- Record feedback_loop evidence.
- Do not train or fine-tune the model during MVP runtime.
- Do not send learning data outside the local machine.
