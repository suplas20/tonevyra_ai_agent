# Lightroom Bridge Skill

## Purpose
Use a file-based JSON bridge between Python and Lightroom Classic or the fake Lightroom worker.

## Rules
- Python writes request JSON.
- Lightroom/fake worker writes response JSON.
- Python reads response and updates DB/artifacts.
- Request payload must use normalized absolute `source_path` and `export_path`.

## Do Not
- Do not run AI inside Lua.
- Do not access PostgreSQL from Lua.
- Do not quality-score inside Lua.
- Do not modify Lightroom catalog files directly from Python.
