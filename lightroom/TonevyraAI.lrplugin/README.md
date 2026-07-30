# Tonevyra AI Lightroom Plugin

This plugin is a Lightroom Classic apply adapter for T-019.

Runtime flow:

1. Tonevyra agent writes `runtime/bridge/lightroom_apply_requests/<request_id>.json`.
2. The plugin reads the request.
3. The plugin applies the allowed Develop settings to the `source_path` photo.
4. The plugin writes `runtime/bridge/lightroom_apply_results/<request_id>.json`.

`BridgeConfig.lua` provides the absolute bridge root. The Windows installer
rewrites it for the installed per-user application path.

The plugin does not run AI analysis, connect to the database, score quality, or modify source image files.
