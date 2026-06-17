# Harness Prompt - T-019 Folder-Driven Lightroom Plugin

Validate that the Lightroom plugin implementation preserves the Tonevyra product concept:

- User drops photos into configured input folder.
- Python agent detects and processes photos.
- Lightroom plugin applies agent-created settings.
- The plugin is not a selected-photo correction tool.

Required checks:

1. Plugin structure exists.
2. Plugin has Tonevyra identity.
3. Plugin has worker/init bridge behavior.
4. Plugin uses `lightroom_apply_requests` and `lightroom_apply_results`.
5. Plugin does not contain selected-photo trigger tokens.
6. Bridge request/result schemas pass.
7. Worker mapping only allows MVP develop settings.
8. Live evidence proves folder-driven application.
