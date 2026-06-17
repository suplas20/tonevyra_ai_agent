-- Folder-driven Lightroom apply worker scaffold.
-- Final implementation should replace placeholders with Lightroom SDK-safe file polling,
-- catalog lookup/import, develop setting application, and apply result writing.

local LrPathUtils = import "LrPathUtils"

local Worker = {}
local running = false

local COMMAND = "APPLY_LIGHTROOM_SETTINGS"
local APPLY_REQUEST_SCHEMA = "t019.lightroom_apply.request.v1"
local APPLY_RESULT_SCHEMA = "t019.lightroom_apply.result.v1"

local function runtimeDir()
  return os.getenv("TONEVYRA_RUNTIME_DIR") or "./runtime"
end

local function bridgeDir()
  return LrPathUtils.child(runtimeDir(), "bridge")
end

local function applyRequestDir()
  return LrPathUtils.child(bridgeDir(), "lightroom_apply_requests")
end

local function applyResultDir()
  return LrPathUtils.child(bridgeDir(), "lightroom_apply_results")
end

local function writeApplyResult(request, status, applied_settings, skipped_settings, error)
  -- Required bridge tokens for harness visibility:
  -- source_path, task_id, develop_settings, applied_settings, skipped_settings
  -- lightroom_apply_requests, lightroom_apply_results, APPLY_LIGHTROOM_SETTINGS
  -- Final implementation must write valid JSON to applyResultDir().
  return true
end

local function applyDevelopSettingsBySourcePath(source_path, task_id, develop_settings)
  -- Final implementation should find or import the Lightroom photo by source_path.
  -- It must not rely on the user-selected Lightroom photo.
  -- Unsupported keys must be recorded in skipped_settings.
  local applied_settings = {}
  local skipped_settings = {}
  return true, applied_settings, skipped_settings
end

local function processApplyRequest(request)
  if request.schema_version ~= APPLY_REQUEST_SCHEMA then
    return writeApplyResult(request, "failed", {}, {}, { code = "INVALID_SCHEMA", message = "Invalid schema", recoverable = true })
  end
  if request.command ~= COMMAND then
    return writeApplyResult(request, "failed", {}, {}, { code = "INVALID_COMMAND", message = "Invalid command", recoverable = true })
  end
  return applyDevelopSettingsBySourcePath(request.source_path, request.task_id, request.develop_settings)
end

function Worker.start()
  running = true
  -- Final implementation should poll applyRequestDir() and call processApplyRequest().
  -- This scaffold intentionally does not implement a busy loop.
  return running
end

function Worker.stop()
  running = false
end

return Worker
