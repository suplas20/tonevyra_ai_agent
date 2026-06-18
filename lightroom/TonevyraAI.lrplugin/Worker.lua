local LrApplication = import "LrApplication"
local LrFileUtils = import "LrFileUtils"

local Bridge = require "Bridge"
local Json = require "Json"

local Worker = {}

local running = false
local activeJob = false
local last_error = nil
local ORIGIN = "lightroom_" .. "plugin"
local PLUGIN_VERSION = "t019-lightroom-apply-adapter-20260618-10"

local KEY_MAP = {
  Exposure = "Exposure2012",
  Contrast = "Contrast2012",
  Highlights = "Highlights2012",
  Shadows = "Shadows2012",
  Whites = "Whites2012",
  Blacks = "Blacks2012",
  Temp = "Temperature",
  Tint = "Tint",
  Vibrance = "Vibrance",
  Saturation = "Saturation",
  Texture = "Texture",
  Clarity = "Clarity2012",
  Dehaze = "Dehaze",
  Sharpening = "Sharpness",
  NoiseReduction = "LuminanceSmoothing",
  exposure = "Exposure2012",
  contrast = "Contrast2012",
  highlights = "Highlights2012",
  shadows = "Shadows2012",
  whites = "Whites2012",
  blacks = "Blacks2012",
  temp = "Temperature",
  tint = "Tint",
  vibrance = "Vibrance",
  saturation = "Saturation",
  texture = "Texture",
  clarity = "Clarity2012",
  dehaze = "Dehaze",
  sharpening = "Sharpness",
  noise_reduction = "LuminanceSmoothing",
}

local RANGES = {
  Exposure = { -5.0, 5.0 },
  Contrast = { -100, 100 },
  Highlights = { -100, 100 },
  Shadows = { -100, 100 },
  Whites = { -100, 100 },
  Blacks = { -100, 100 },
  Temp = { 1500, 50000 },
  Tint = { -150, 150 },
  Vibrance = { -100, 100 },
  Saturation = { -100, 100 },
  Texture = { -100, 100 },
  Clarity = { -100, 100 },
  Dehaze = { -100, 100 },
  Sharpening = { 0, 150 },
  NoiseReduction = { 0, 100 },
  exposure = { -5.0, 5.0 },
  contrast = { -100, 100 },
  highlights = { -100, 100 },
  shadows = { -100, 100 },
  whites = { -100, 100 },
  blacks = { -100, 100 },
  temp = { 1500, 50000 },
  tint = { -150, 150 },
  vibrance = { -100, 100 },
  saturation = { -100, 100 },
  texture = { -100, 100 },
  clarity = { -100, 100 },
  dehaze = { -100, 100 },
  sharpening = { 0, 150 },
  noise_reduction = { 0, 100 },
}

local function now()
  return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

local function clamp(value, low, high)
  if value < low then
    return low
  end
  if value > high then
    return high
  end
  return value
end

local function baseResult(request, status)
  return {
    schema_version = "t019.lightroom_apply.result.v1",
    request_id = tostring(request.request_id or "unknown"),
    request_origin = ORIGIN,
    command = "APPLY_LIGHTROOM_SETTINGS",
    task_id = tostring(request.task_id or "unknown"),
    status = status,
    source_path = tostring(request.source_path or ""),
    catalog_action = "unknown",
    applied_parameters = {},
    skipped_parameters = {},
    applied_settings = {},
    skipped_settings = {},
    error_code = nil,
    message = "",
    completed_at = now(),
    lightroom_result = {
      plugin_loaded = true,
      plugin_version = PLUGIN_VERSION,
      worker_running = running,
      source_photo_found = false,
      source_photo_imported = false,
      develop_settings_applied = false,
    },
    evidence = {
      applied_at = now(),
      adapter_role = "apply_adapter",
      trigger = tostring(request.trigger or "bridge_request"),
    },
  }
end

local function failed(request, code, message, recoverable)
  local result = baseResult(request or {}, "failed")
  result.catalog_action = "not_imported"
  result.error_code = code
  result.message = message
  result.error = {
    code = code,
    message = message,
    recoverable = recoverable,
  }
  return result
end

local function validate(request)
  if type(request) ~= "table" then
    return false, "INVALID_JSON", "Request JSON did not decode to an object."
  end
  if request.schema_version ~= "t019.lightroom_apply.request.v1" and request.schema_version ~= "1.0" then
    return false, "INVALID_SCHEMA", "Unsupported apply request schema."
  end
  if request.request_origin ~= nil and request.request_origin ~= "tonevyra_agent" then
    return false, "INVALID_ORIGIN", "Apply request origin must be tonevyra_agent."
  end
  if request.command ~= nil and request.command ~= "APPLY_LIGHTROOM_SETTINGS" then
    return false, "INVALID_COMMAND", "Unsupported Lightroom command."
  end
  if request.operation ~= nil and request.operation ~= "apply_develop_settings" then
    return false, "INVALID_OPERATION", "Unsupported Lightroom apply operation."
  end
  if type(request.task_id) ~= "string" or request.task_id == "" then
    return false, "MISSING_TASK_ID", "task_id is required."
  end
  if type(request.source_path) ~= "string" or request.source_path == "" then
    return false, "MISSING_SOURCE_PATH", "source_path is required."
  end
  if type(request.develop_settings) ~= "table" then
    return false, "MISSING_DEVELOP_SETTINGS", "develop_settings is required."
  end
  if request.safety ~= nil and (type(request.safety) ~= "table" or request.safety.non_destructive_required ~= true) then
    return false, "SAFETY_REQUIRED", "non_destructive_required must be true when safety is supplied."
  end
  return true, nil, nil
end

local function mapSettings(settings)
  local develop = {}
  local applied = {}
  local skipped = {}
  for key, value in pairs(settings) do
    local lrKey = KEY_MAP[key]
    local range = RANGES[key]
    local number = tonumber(value)
    if not lrKey then
      skipped[key] = { reason = "unsupported_parameter", value = value }
    elseif not number then
      skipped[key] = { reason = "non_numeric", value = value }
    else
      local clamped = clamp(number, range[1], range[2])
      develop[lrKey] = clamped
      applied[key] = clamped
      if clamped ~= number then
        skipped[key .. "_clamp"] = { reason = "clamped", value = number, applied = clamped }
      end
    end
  end
  return develop, applied, skipped
end

local function findPhoto(catalog, sourcePath)
  local found = false
  local imported = false
  local photo = nil

  local okSearch, photos = pcall(function()
    return catalog:findPhotos { searchDesc = sourcePath }
  end)
  if okSearch and type(photos) == "table" and #photos > 0 then
    photo = photos[1]
    found = true
  end

  if not photo then
    local okImport, importedPhoto = pcall(function()
      return catalog:addPhoto(sourcePath)
    end)
    if okImport and importedPhoto then
      photo = importedPhoto
      imported = true
    end
  end

  return photo, found, imported
end

local function findExistingPhoto(catalog, sourcePath)
  local okSearch, photos = pcall(function()
    return catalog:findPhotos { searchDesc = sourcePath }
  end)
  if okSearch and type(photos) == "table" and #photos > 0 then
    return photos[1]
  end
  return nil
end

local function directApplyFallback(catalog, sourcePath, develop)
  local sourceFound = false
  local sourceImported = false
  local photo = findExistingPhoto(catalog, sourcePath)
  if photo then
    sourceFound = true
  else
    local okImport, importedPhoto = pcall(function()
      return catalog:addPhoto(sourcePath)
    end)
    if okImport and importedPhoto then
      photo = importedPhoto
      sourceImported = true
    else
      return nil, sourceFound, sourceImported, "direct_import_failed: " .. tostring(importedPhoto)
    end
  end

  local okApply, applyErr = pcall(function()
    photo:applyDevelopSettings(develop)
  end)
  if not okApply then
    return nil, sourceFound, sourceImported, "direct_apply_failed: " .. tostring(applyErr)
  end
  return photo, sourceFound, sourceImported, nil
end

local function applyRequest(request)
  request.trigger = request.trigger or "bridge_request"
  local ok, code, message = validate(request)
  if not ok then
    return failed(request, code, message, true)
  end

  if not LrFileUtils.exists(request.source_path) then
    return failed(request, "SOURCE_PATH_NOT_FOUND", "The source_path file from the Agent apply request does not exist.", true)
  end

  local develop, applied, skipped = mapSettings(request.develop_settings)
  if next(applied) == nil then
    local result = failed(request, "NO_SUPPORTED_SETTINGS", "No supported Develop settings were supplied.", true)
    result.skipped_settings = skipped
    return result
  end

  local result = baseResult(request, "applied")
  result.applied_parameters = applied
  result.skipped_parameters = skipped
  result.applied_settings = applied
  result.skipped_settings = skipped

  local catalog = LrApplication.activeCatalog()
  local photo = nil
  local sourceFound = false
  local sourceImported = false

  local writeOk, writeErr = pcall(function()
    catalog:withWriteAccessDo("Tonevyra AI Apply Settings", function()
      photo, sourceFound, sourceImported = findPhoto(catalog, request.source_path)
      if photo then
        photo:applyDevelopSettings(develop)
      end
    end, { timeoutInSeconds = 30 })
  end)

  if not writeOk then
    local fallbackPhoto, fallbackFound, fallbackImported, fallbackErr = directApplyFallback(catalog, request.source_path, develop)
    if fallbackPhoto then
      result.lightroom_result.source_photo_found = fallbackFound
      result.lightroom_result.source_photo_imported = fallbackImported
      result.lightroom_result.develop_settings_applied = true
      result.evidence.write_access_error = tostring(writeErr)
      result.evidence.write_access_fallback = "direct_apply"
      result.catalog_action = "found_existing"
      if fallbackImported then
        result.status = "partial"
        result.catalog_action = "imported"
      end
      result.message = "Applied successfully through direct Lightroom API fallback"
      return result
    else
      local failedResult = failed(request, "LIGHTROOM_WRITE_ACCESS_BLOCKED", tostring(writeErr), true)
      failedResult.applied_parameters = {}
      failedResult.applied_settings = {}
      failedResult.skipped_parameters = skipped
      failedResult.skipped_settings = skipped
      failedResult.lightroom_result.source_photo_found = fallbackFound or sourceFound
      failedResult.lightroom_result.source_photo_imported = fallbackImported or sourceImported
      failedResult.evidence.write_access_fallback = "direct_apply_failed"
      failedResult.evidence.fallback_error = tostring(fallbackErr)
      failedResult.message = tostring(writeErr) .. "; fallback failed: " .. tostring(fallbackErr)
      failedResult.error.message = failedResult.message
      return failedResult
    end
  end

  result.lightroom_result.source_photo_found = sourceFound
  result.lightroom_result.source_photo_imported = sourceImported
  result.lightroom_result.develop_settings_applied = photo ~= nil
  result.catalog_action = "found_existing"
  if sourceImported then
    result.status = "partial"
    result.catalog_action = "imported"
  end
  if not photo then
    return failed(request, "LIGHTROOM_PHOTO_NOT_AVAILABLE", "Lightroom could not attach the source path.", true)
  end
  result.message = "Applied successfully"
  return result
end

local function writeResult(result)
  local json = Json.encode(result)
  local ok, err = Bridge.writeResult(result.request_id, json)
  if not ok then
    last_error = err
  end
  Bridge.writeEvidence(result.request_id, json)
end

local function processClaimedPath(claimed, trigger)
  local text, readErr = Bridge.read(claimed)
  if not text then
    writeResult(failed({ request_id = "unknown" }, "REQUEST_READ_FAILED", readErr or "Unable to read apply request.", true))
    Bridge.moveError(claimed)
    return
  end

  local ok, request = pcall(function()
    return Json.decode(text)
  end)
  if not ok then
    writeResult(failed({ request_id = "unknown" }, "REQUEST_JSON_INVALID", "Apply request JSON could not be parsed.", true))
    Bridge.moveError(claimed)
    return
  end
  request.trigger = trigger or "bridge_request"

  local okApply, result = pcall(function()
    return applyRequest(request)
  end)
  if not okApply then
    result = failed(request, "LIGHTROOM_APPLY_FAILED", tostring(result), true)
  end
  writeResult(result)
  if result.status == "failed" then
    Bridge.moveError(claimed)
  else
    Bridge.moveProcessed(claimed)
  end
end

local function processPath(path)
  if activeJob then
    return
  end
  local claimed = Bridge.claim(path)
  if not claimed then
    return
  end
  activeJob = true
  local ok, err = pcall(function()
    processClaimedPath(claimed, "manual_menu")
  end)
  if not ok then
    last_error = tostring(err)
  end
  activeJob = false
end

function Worker.start()
  if running then
    return
  end
  running = true
  Bridge.ensureDirs()
  Bridge.writeWorkerStatus(true, last_error)
  return true
end

function Worker.processOnePending(trigger)
  Bridge.ensureDirs()
  local ok, items = pcall(function()
    return Bridge.pendingRequests()
  end)
  if not ok then
    last_error = tostring(items)
    Bridge.writeWorkerStatus(running, last_error)
    return "Bridge request scan failed: " .. last_error
  end
  if not items or #items == 0 then
    Bridge.writeWorkerStatus(running, last_error)
    return "No pending apply request."
  end
  processPath(items[1])
  Bridge.writeWorkerStatus(running, last_error)
  return "Processed apply request: " .. tostring(items[1])
end

function Worker.stop()
  running = false
  Bridge.writeWorkerStatus(false, last_error)
end

function Worker.status()
  Bridge.ensureDirs()
  local persisted = Bridge.readWorkerStatus()
  if persisted then
    return persisted
  end
  return {
    worker_running = tostring(running),
    request_dir = Bridge.request_dir,
    result_dir = Bridge.result_dir,
    last_error = last_error or "",
  }
end

return Worker
