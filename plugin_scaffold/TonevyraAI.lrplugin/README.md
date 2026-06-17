# TonevyraAI.lrplugin folder-driven scaffold

This scaffold is included only to give Codex a safe starting shape. It is not a completed plugin.

Required implementation work:

- Add safe JSON encoding/decoding.
- Add `lightroom_apply_requests` polling.
- Add request validation.
- Find or import Lightroom photo by `source_path`.
- Apply allowed Develop parameter mapping.
- Write `lightroom_apply_results` JSON.
- Keep Lua as a thin apply worker only.
- Do not use the currently selected Lightroom photo as the workflow trigger.
