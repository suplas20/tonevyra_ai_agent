# Lightroom Bridge Skill

## Purpose

Use this skill for the file-based bridge between the Python Agent and Lightroom-side adapters or fake workers.

The bridge is a request/result transport. It is not a folder watcher, model runner, quality gate, or orchestration engine.

## Responsibilities

- Python Agent writes request JSON.
- Fake Lightroom worker or real Lightroom Apply Adapter writes result/response JSON.
- Python Agent ingests the result and updates DB/artifacts/task events.
- Request payloads must use normalized absolute `source_path` values when identifying source images.
- For real Lightroom Classic work, use the `lightroom-apply-adapter` skill.

## Real Lightroom Apply Adapter Boundary

For T-019 and later Lightroom Classic plugin work:

```text
Agent-created apply request
→ runtime\bridge\lightroom_apply_requests\<request_id>.json
→ Lightroom Apply Adapter plugin
→ runtime\bridge\lightroom_apply_results\<request_id>.json
→ Agent result ingestion
```

The plugin must not watch `runtime\input`. The Agent owns folder watching and correction planning.

## Fake Lightroom Boundary

Fake Lightroom remains available for harness and regression work. It may simulate request/response/export behavior, but it must not redefine the real Lightroom Classic plugin role.

## Do Not

- Do not run AI inside Lua.
- Do not access PostgreSQL from Lua.
- Do not quality-score inside Lua.
- Do not modify Lightroom catalog files directly from Python.
- Do not make the plugin responsible for input folder detection.
- Do not make selected Lightroom photo the primary product workflow.
