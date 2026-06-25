local LrApplication = import "LrApplication"
local LrExportSession = import "LrExportSession"
local LrFileUtils = import "LrFileUtils"
local LrFunctionContext = import "LrFunctionContext"
local LrPathUtils = import "LrPathUtils"
local LrTasks = import "LrTasks"

local Bridge = require "Bridge"
local Json = require "Json"

local Worker = {}

local running = false
local start_requested = false
local activeJob = false
local last_error = nil
local ORIGIN = "lightroom_" .. "plugin"
local PLUGIN_VERSION = Bridge.plugin_version

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
  red_saturation = "SaturationAdjustmentRed",
  orange_saturation = "SaturationAdjustmentOrange",
  yellow_saturation = "SaturationAdjustmentYellow",
  green_saturation = "SaturationAdjustmentGreen",
  aqua_saturation = "SaturationAdjustmentAqua",
  blue_saturation = "SaturationAdjustmentBlue",
  purple_saturation = "SaturationAdjustmentPurple",
  magenta_saturation = "SaturationAdjustmentMagenta",
  red_hue = "HueAdjustmentRed",
  orange_hue = "HueAdjustmentOrange",
  yellow_hue = "HueAdjustmentYellow",
  green_hue = "HueAdjustmentGreen",
  aqua_hue = "HueAdjustmentAqua",
  blue_hue = "HueAdjustmentBlue",
  purple_hue = "HueAdjustmentPurple",
  magenta_hue = "HueAdjustmentMagenta",
  red_luminance = "LuminanceAdjustmentRed",
  orange_luminance = "LuminanceAdjustmentOrange",
  yellow_luminance = "LuminanceAdjustmentYellow",
  green_luminance = "LuminanceAdjustmentGreen",
  aqua_luminance = "LuminanceAdjustmentAqua",
  blue_luminance = "LuminanceAdjustmentBlue",
  purple_luminance = "LuminanceAdjustmentPurple",
  magenta_luminance = "LuminanceAdjustmentMagenta",
}

local RANGES = {
  Exposure = { -5.0, 5.0 },
  Contrast = { -100, 100 },
  Highlights = { -100, 100 },
  Shadows = { -100, 100 },
  Whites = { -100, 100 },
  Blacks = { -100, 100 },
  Temp = { 2500, 50000 },
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
  temp = { 2500, 50000 },
  temperature_delta = { -3500, 3500 },
  tint = { -150, 150 },
  vibrance = { -100, 100 },
  saturation = { -100, 100 },
  texture = { -100, 100 },
  clarity = { -100, 100 },
  dehaze = { -100, 100 },
  sharpening = { 0, 150 },
  noise_reduction = { 0, 100 },
  red_saturation = { -100, 100 },
  orange_saturation = { -100, 100 },
  yellow_saturation = { -100, 100 },
  green_saturation = { -100, 100 },
  aqua_saturation = { -100, 100 },
  blue_saturation = { -100, 100 },
  purple_saturation = { -100, 100 },
  magenta_saturation = { -100, 100 },
  red_hue = { -100, 100 },
  orange_hue = { -100, 100 },
  yellow_hue = { -100, 100 },
  green_hue = { -100, 100 },
  aqua_hue = { -100, 100 },
  blue_hue = { -100, 100 },
  purple_hue = { -100, 100 },
  magenta_hue = { -100, 100 },
  red_luminance = { -100, 100 },
  orange_luminance = { -100, 100 },
  yellow_luminance = { -100, 100 },
  green_luminance = { -100, 100 },
  aqua_luminance = { -100, 100 },
  blue_luminance = { -100, 100 },
  purple_luminance = { -100, 100 },
  magenta_luminance = { -100, 100 },
}

local function now()
  return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

local function safeWriteWorkerStatus(isRunning)
  local ok, err = pcall(function()
    Bridge.writeWorkerStatus(isRunning, last_error, start_requested)
  end)
  if not ok then
    last_error = tostring(err)
  end
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

local function needsTemperatureBase(settings)
  return settings ~= nil and settings.temperature_delta ~= nil
end

local function readDevelopSettingsWithRetry(photo)
  local lastSettings = nil
  local lastError = nil
  local attempt = 0
  while attempt < 5 do
    attempt = attempt + 1
    local ok, settings = LrFunctionContext.pcallWithContext("tonevyra_read_develop_settings", function(context)
      return photo:getDevelopSettings()
    end)
    if ok and type(settings) == "table" then
      lastSettings = settings
      if tonumber(settings.Temperature) ~= nil then
        return settings, nil, attempt
      end
    else
      lastError = tostring(settings)
    end
    LrTasks.sleep(0.4)
  end
  return lastSettings, lastError or "Temperature was not available in Lightroom develop settings.", attempt
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
    write_access_retry_count = 0,
    write_access_wait_ms = 0,
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
      local_adjustments_requested = request.local_adjustments ~= nil,
      local_adjustments_applied = false,
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

local function fileSize(path)
  local handle = io.open(path, "rb")
  if not handle then
    return 0
  end
  local size = handle:seek("end") or 0
  handle:close()
  return size
end

local function baseExportResult(request, status)
  local exportPath = tostring(request.export_path or "")
  local exists = exportPath ~= "" and LrFileUtils.exists(exportPath)
  return {
    schema_version = "t020.lightroom_export.result.v1",
    request_id = tostring(request.request_id or "unknown"),
    task_id = tostring(request.task_id or "unknown"),
    apply_request_id = tostring(request.apply_request_id or "unknown"),
    source_path = tostring(request.source_path or ""),
    export_path = exportPath,
    status = status,
    export_settings = request.export_settings or {
      format = "JPEG",
      quality = 95,
      color_space = "sRGB",
      resize = false,
    },
    lightroom_result = {
      plugin_loaded = true,
      plugin_version = PLUGIN_VERSION,
      worker_running = running,
      source_photo_found = false,
      export_started = false,
      export_completed = false,
    },
    file_result = {
      exists = exists,
      size_bytes = exists and fileSize(exportPath) or 0,
    },
    error_code = nil,
    message = "",
    completed_at = now(),
  }
end

local function normalizeExportErrorCode(code)
  if code == "LIGHTROOM_REQUEST_FAILED"
    or code == "LIGHTROOM_RESPONSE_TIMEOUT"
    or code == "LIGHTROOM_EXPORT_FAILED"
    or code == "EXPORT_FILE_MISSING"
    or code == "ARTIFACT_WRITE_FAILED"
    or code == "DB_WRITE_FAILED" then
    return code
  end
  if code == "EXPORT_FILE_MISSING" then
    return "EXPORT_FILE_MISSING"
  end
  if code == "LIGHTROOM_EXPORT_FAILED" or code == "SOURCE_PHOTO_NOT_FOUND" then
    return "LIGHTROOM_EXPORT_FAILED"
  end
  return "LIGHTROOM_REQUEST_FAILED"
end

local function exportFailed(request, code, message, recoverable)
  local result = baseExportResult(request or {}, "failed")
  result.error_code = normalizeExportErrorCode(code)
  result.recoverable = recoverable
  result.message = tostring(code) .. ": " .. tostring(message)
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

local function validateExportRequest(request)
  if type(request) ~= "table" then
    return false, "INVALID_JSON", "Export request JSON did not decode to an object."
  end
  if request.schema_version ~= "t020.lightroom_export.request.v1" then
    return false, "INVALID_SCHEMA", "Unsupported export request schema."
  end
  if request.command ~= "EXPORT_CORRECTED_IMAGE" then
    return false, "INVALID_COMMAND", "Unsupported Lightroom export command."
  end
  if type(request.request_id) ~= "string" or request.request_id == "" then
    return false, "MISSING_REQUEST_ID", "request_id is required."
  end
  if type(request.task_id) ~= "string" or request.task_id == "" then
    return false, "MISSING_TASK_ID", "task_id is required."
  end
  if type(request.apply_request_id) ~= "string" or request.apply_request_id == "" then
    return false, "MISSING_APPLY_REQUEST_ID", "apply_request_id is required."
  end
  if type(request.source_path) ~= "string" or request.source_path == "" then
    return false, "MISSING_SOURCE_PATH", "source_path is required."
  end
  if type(request.export_path) ~= "string" or request.export_path == "" then
    return false, "MISSING_EXPORT_PATH", "export_path is required."
  end
  if request.source_path == request.export_path then
    return false, "INVALID_EXPORT_PATH", "export_path must not equal source_path."
  end
  local normalized = string.lower(request.export_path)
  if not string.find(normalized, "\\runtime\\output\\temp\\", 1, true) then
    return false, "INVALID_EXPORT_PATH", "export_path must stay under runtime\\output\\temp."
  end
  if type(request.export_settings) ~= "table" then
    return false, "MISSING_EXPORT_SETTINGS", "export_settings is required."
  end
  if request.export_settings.format ~= "JPEG" then
    return false, "UNSUPPORTED_EXPORT_FORMAT", "MVP export format must be JPEG."
  end
  if request.export_settings.color_space ~= "sRGB" then
    return false, "UNSUPPORTED_COLOR_SPACE", "MVP export color_space must be sRGB."
  end
  if request.export_settings.resize ~= false then
    return false, "UNSUPPORTED_RESIZE", "MVP export resize must be false."
  end
  if request.export_settings.overwrite ~= false then
    return false, "OVERWRITE_FORBIDDEN", "Export overwrite must be false."
  end
  return true, nil, nil
end

local function mapSettings(settings, baseDevelopSettings)
  local develop = {}
  local applied = {}
  local skipped = {}
  for key, value in pairs(settings) do
    local lrKey = KEY_MAP[key]
    local range = RANGES[key]
    local number = tonumber(value)
    if key == "temperature_delta" then
      if not number then
        skipped[key] = { reason = "non_numeric", value = value }
      else
        local baseTemperature = tonumber(baseDevelopSettings and baseDevelopSettings.Temperature)
        if not baseTemperature then
          skipped[key] = { reason = "base_temperature_unavailable", value = value }
        else
          local delta = clamp(number, range[1], range[2])
          local target = clamp(baseTemperature + delta, RANGES.temp[1], RANGES.temp[2])
          develop.Temperature = target
          applied[key] = delta
          applied.temp = target
          if delta ~= number then
            skipped[key .. "_clamp"] = { reason = "clamped", value = number, applied = delta }
          end
          if target ~= baseTemperature + delta then
            skipped.temp_clamp = { reason = "clamped", value = baseTemperature + delta, applied = target }
          end
          skipped.temperature_resolution = {
            reason = "resolved_relative_delta_to_absolute_temperature",
            base = baseTemperature,
            base_reason = "lightroom_current_temperature",
            delta = delta,
            applied = target,
          }
        end
      end
    elseif not lrKey then
      skipped[key] = { reason = "unsupported_parameter", value = value }
    elseif not number then
      skipped[key] = { reason = "non_numeric", value = value }
    elseif (key == "temp" or key == "Temp") and number < range[1] then
      skipped[key] = {
        reason = "temperature_must_be_absolute_not_delta",
        value = number,
        minimum_absolute_temperature = range[1],
      }
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

-- Catalog write-access tuning. Every catalog mutation (addPhoto / applyDevelopSettings)
-- must run inside withWriteAccessDo with an explicit timeout, and a block by another
-- write-access call must be retried rather than closed as a final failure immediately.
local WRITE_TIMEOUT_SECONDS = 15
local WRITE_MAX_ATTEMPTS = 4
local WRITE_RETRY_WAIT_SECONDS = 1.0

-- Read-only stage: resolve an existing catalog photo by path. This must not acquire
-- write access. findPhotoByPath is the canonical read-only lookup for a file path.
-- The protected call uses the SDK's yield-safe pcallWithContext (never a plain Lua
-- pcall) so a yielding Lightroom API call cannot trip "Yielding is not allowed within
-- a C or metamethod call".
local function resolveExistingPhoto(catalog, sourcePath)
  local ok, photo = LrFunctionContext.pcallWithContext("tonevyra_find_photo", function(context)
    return catalog:findPhotoByPath(sourcePath)
  end)
  if ok and photo then
    return photo
  end
  return nil
end

-- Write-access stage: import the source photo (if not already in the catalog) and apply
-- the Develop settings. All catalog mutations happen strictly inside withWriteAccessDo.
--
-- Yield safety rules enforced here:
--   * withWriteAccessDo / addPhoto / applyDevelopSettings all yield, so they are wrapped
--     only by the SDK's yield-safe pcallWithContext, never a plain Lua pcall.
--   * The withWriteAccessDo callback does no sleeping, retrying, or dialogs.
--   * A blocked catalog is reported via callbackTimeoutFunction (no thrown error), and
--     the retry wait (LrTasks.sleep) runs OUTSIDE withWriteAccessDo.
--   * write_access_retry_count / write_access_wait_ms only grow when a retry is actually
--     performed.
local function applyWithWriteAccess(catalog, sourcePath, settings, existingPhoto)
  local outcome = {
    photo = existingPhoto,
    found = existingPhoto ~= nil,
    imported = false,
    applied = false,
    applied_settings = {},
    skipped_settings = {},
    retry_count = 0,
    wait_ms = 0,
    blocked = false,
    error = nil,
  }

  if not outcome.photo then
    local importAttempt = 0
    while importAttempt < WRITE_MAX_ATTEMPTS do
      importAttempt = importAttempt + 1
      local importInnerError = nil
      local importTimedOut = false
      local importOk, importErr = LrFunctionContext.pcallWithContext(
        "tonevyra_import_photo",
        function(context)
          catalog:withWriteAccessDo(
            "Tonevyra AI Import Photo",
            function()
              local importedPhoto = catalog:addPhoto(sourcePath)
              if not importedPhoto then
                importInnerError = "import_failed: addPhoto returned nil"
                return
              end
              outcome.photo = importedPhoto
              outcome.imported = true
            end,
            {
              timeout = WRITE_TIMEOUT_SECONDS,
              callbackTimeoutFunction = function()
                importTimedOut = true
              end,
            }
          )
        end
      )
      if outcome.photo then
        LrTasks.sleep(0.6)
        break
      end
      if not importOk then
        outcome.blocked = false
        outcome.error = "import_callback_error: " .. tostring(importErr)
        return outcome
      end
      if importInnerError ~= nil then
        outcome.blocked = false
        outcome.error = importInnerError
        return outcome
      end
      outcome.blocked = true
      if importTimedOut then
        outcome.error = "write access blocked during import: catalog busy, timed out after "
          .. tostring(WRITE_TIMEOUT_SECONDS) .. "s"
      else
        outcome.error = "write access not granted during import"
      end
      if importAttempt < WRITE_MAX_ATTEMPTS then
        LrTasks.sleep(WRITE_RETRY_WAIT_SECONDS)
        outcome.retry_count = outcome.retry_count + 1
        outcome.wait_ms = outcome.wait_ms + math.floor(WRITE_RETRY_WAIT_SECONDS * 1000 + 0.5)
      end
    end
    if not outcome.photo then
      return outcome
    end
  end

  local attempt = 0
  while attempt < WRITE_MAX_ATTEMPTS do
    attempt = attempt + 1

    local innerError = nil
    local timedOut = false
    local baseDevelopSettings = nil
    if needsTemperatureBase(settings) then
      -- Reset white balance to "As Shot" in its OWN committed write transaction
      -- BEFORE reading the base temperature. A same-transaction reset+reread is
      -- unreliable (Lightroom applies asynchronously), which let temperature_delta
      -- accumulate onto a previously corrected value across reprocessing/retries.
      -- A separate committed transaction guarantees the base read sees the
      -- original as-shot temperature, making temperature_delta idempotent.
      LrFunctionContext.pcallWithContext("tonevyra_reset_wb", function(context)
        catalog:withWriteAccessDo(
          "Tonevyra AI Reset WhiteBalance",
          function()
            outcome.photo:applyDevelopSettings({ WhiteBalance = "As Shot" })
          end,
          { timeout = WRITE_TIMEOUT_SECONDS }
        )
      end)

      local readError = nil
      local readAttempts = 0
      baseDevelopSettings, readError, readAttempts = readDevelopSettingsWithRetry(outcome.photo)
      outcome.evidence_read_attempts = readAttempts
      outcome.as_shot_temperature = tonumber(baseDevelopSettings and baseDevelopSettings.Temperature)
      if tonumber(baseDevelopSettings and baseDevelopSettings.Temperature) == nil then
        outcome.blocked = false
        outcome.error = "base_temperature_unavailable: " .. tostring(readError)
        return outcome
      end
    end

    local protectedOk, protectedErr = LrFunctionContext.pcallWithContext(
      "tonevyra_write_access",
      function(context)
        catalog:withWriteAccessDo(
          "Tonevyra AI Apply Settings",
          function()
            -- baseDevelopSettings was captured after an As Shot reset committed
            -- in a separate transaction above, so it is the original as-shot WB.
            local develop, applied, skipped = mapSettings(settings, baseDevelopSettings)
            outcome.applied_settings = applied
            outcome.skipped_settings = skipped
            if next(applied) == nil then
              innerError = "no_supported_settings"
              return
            end
            outcome.photo:applyDevelopSettings(develop)
            outcome.applied = true
          end,
          {
            timeout = WRITE_TIMEOUT_SECONDS,
            callbackTimeoutFunction = function()
              timedOut = true
            end,
          }
        )
      end
    )

    if outcome.applied then
      outcome.blocked = false
      outcome.error = nil
      return outcome
    end

    if not protectedOk then
      -- A thrown error inside the write-access gate (import/apply). Retrying will not help.
      outcome.blocked = false
      outcome.error = "write_callback_error: " .. tostring(protectedErr)
      return outcome
    end

    if innerError ~= nil then
      -- Import/apply reported a soft failure. Retrying will not help.
      outcome.blocked = false
      outcome.error = innerError
      return outcome
    end

    -- Callback never ran: write access was not granted within the timeout (catalog busy).
    outcome.blocked = true
    if timedOut then
      outcome.error = "write access blocked: catalog busy, timed out after "
        .. tostring(WRITE_TIMEOUT_SECONDS) .. "s"
    else
      outcome.error = "write access not granted"
    end

    if attempt < WRITE_MAX_ATTEMPTS then
      -- Retry wait happens OUTSIDE withWriteAccessDo (and outside any plain Lua pcall).
      LrTasks.sleep(WRITE_RETRY_WAIT_SECONDS)
      outcome.retry_count = outcome.retry_count + 1
      outcome.wait_ms = outcome.wait_ms + math.floor(WRITE_RETRY_WAIT_SECONDS * 1000 + 0.5)
    end
  end

  return outcome
end

local function recordWriteEvidence(result, outcome)
  result.write_access_retry_count = outcome.retry_count
  result.write_access_wait_ms = outcome.wait_ms
  result.evidence.write_access_retry_count = outcome.retry_count
  result.evidence.write_access_wait_ms = outcome.wait_ms
  if outcome.error then
    result.evidence.write_access_error = tostring(outcome.error)
  end
  if outcome.evidence_read_attempts then
    result.evidence.develop_settings_read_attempts = outcome.evidence_read_attempts
  end
end

local function applyRequest(request)
  request.trigger = request.trigger or "bridge_request"
  local ok, code, message = validate(request)
  if not ok then
    return failed(request, code, message, true)
  end

  -- Read-only stage: confirm the source file exists before touching the catalog.
  if not LrFileUtils.exists(request.source_path) then
    return failed(request, "SOURCE_PATH_NOT_FOUND", "The source_path file from the Agent apply request does not exist.", true)
  end

  local catalog = LrApplication.activeCatalog()

  -- Read-only stage: resolve an existing catalog photo by path (no write access taken).
  local existingPhoto = resolveExistingPhoto(catalog, request.source_path)

  -- Write-access stage: import if needed and apply Develop settings, with retry on block.
  local outcome = applyWithWriteAccess(catalog, request.source_path, request.develop_settings, existingPhoto)

  if outcome.applied then
    local result = baseResult(request, "applied")
    result.applied_parameters = outcome.applied_settings
    result.skipped_parameters = outcome.skipped_settings
    result.applied_settings = outcome.applied_settings
    result.skipped_settings = outcome.skipped_settings
    if request.local_adjustments ~= nil then
      result.skipped_settings.local_adjustments = {
        reason = "mask_execution_not_supported_by_current_plugin_adapter",
        requested = true,
      }
      result.skipped_parameters.local_adjustments = result.skipped_settings.local_adjustments
      result.evidence.local_adjustments = {
        requested = true,
        adapter_note = "Agent supplied a planner-owned local adjustment plan, but this plugin version only applies global Develop settings.",
      }
    end
    result.lightroom_result.source_photo_found = outcome.found
    result.lightroom_result.source_photo_imported = outcome.imported
    result.lightroom_result.develop_settings_applied = true
    result.catalog_action = outcome.imported and "imported" or "found_existing"
    recordWriteEvidence(result, outcome)
    result.message = "Applied successfully"
    return result
  end

  -- Failure path: distinguish a recoverable write-access block from a hard import/apply error.
  local errorCode, failMessage
  if outcome.blocked then
    errorCode = "LIGHTROOM_WRITE_ACCESS_BLOCKED"
    failMessage = "Lightroom catalog write access stayed blocked after "
      .. tostring(outcome.retry_count) .. " retries: " .. tostring(outcome.error)
  else
    errorCode = "LIGHTROOM_APPLY_FAILED"
    failMessage = "Lightroom could not import/apply the source_path: " .. tostring(outcome.error)
  end

  local result = failed(request, errorCode, failMessage, true)
  result.skipped_parameters = outcome.skipped_settings
  result.skipped_settings = outcome.skipped_settings
  result.catalog_action = outcome.imported and "imported" or "not_imported"
  result.lightroom_result.source_photo_found = outcome.found
  result.lightroom_result.source_photo_imported = outcome.imported
  result.lightroom_result.develop_settings_applied = false
  recordWriteEvidence(result, outcome)
  return result
end

local function ensureDirectory(path)
  if path and path ~= "" and not LrFileUtils.exists(path) then
    LrFileUtils.createAllDirectories(path)
  end
end

local function exportPhoto(photo, exportPath, exportSettings)
  local exportFolder = LrPathUtils.parent(exportPath)
  local exportName = LrPathUtils.removeExtension(LrPathUtils.leafName(exportPath))
  ensureDirectory(exportFolder)

  local quality = tonumber(exportSettings.quality or 95) or 95
  local exportSession = LrExportSession {
    photosToExport = { photo },
    exportSettings = {
      LR_export_destinationType = "specificFolder",
      LR_export_destinationPathPrefix = exportFolder,
      LR_export_useSubfolder = false,
      LR_format = "JPEG",
      LR_jpeg_quality = quality / 100,
      LR_export_colorSpace = "sRGB",
      LR_size_doConstrain = false,
      LR_outputSharpeningOn = true,
      LR_outputSharpeningMedia = "screen",
      LR_outputSharpeningLevel = 2,
      LR_renamingTokensOn = true,
      LR_tokens = exportName,
    },
  }
  exportSession:doExportOnCurrentTask()
end

local function exportRequest(request)
  request.trigger = request.trigger or "bridge_request"
  local ok, code, message = validateExportRequest(request)
  if not ok then
    return exportFailed(request, code, message, true)
  end

  if not LrFileUtils.exists(request.source_path) then
    return exportFailed(request, "SOURCE_PATH_NOT_FOUND", "The source_path file from the Agent export request does not exist.", true)
  end
  if LrFileUtils.exists(request.export_path) then
    return exportFailed(request, "EXPORT_PATH_EXISTS", "The export_path already exists and overwrite is false.", true)
  end

  local catalog = LrApplication.activeCatalog()
  local photo = resolveExistingPhoto(catalog, request.source_path)
  if not photo then
    return exportFailed(request, "SOURCE_PHOTO_NOT_FOUND", "The corrected catalog photo was not found by source_path.", true)
  end

  local result = baseExportResult(request, "exported")
  result.lightroom_result.source_photo_found = true
  result.lightroom_result.export_started = true

  local exportOk, exportErr = LrFunctionContext.pcallWithContext("tonevyra_export_request", function(context)
    exportPhoto(photo, request.export_path, request.export_settings or {})
  end)

  if not exportOk then
    return exportFailed(request, "LIGHTROOM_EXPORT_FAILED", "Lightroom export failed: " .. tostring(exportErr), true)
  end
  if not LrFileUtils.exists(request.export_path) or fileSize(request.export_path) <= 0 then
    return exportFailed(request, "EXPORT_FILE_MISSING", "Lightroom export did not create a non-empty export_path.", true)
  end

  result.lightroom_result.export_completed = true
  result.file_result.exists = true
  result.file_result.size_bytes = fileSize(request.export_path)
  result.message = "Export completed successfully"
  result.completed_at = now()
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

local function writeExportResult(result)
  local json = Json.encode(result)
  local ok, err = Bridge.writeExportResult(result.request_id, json)
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

  -- Json.decode is pure Lua string parsing and does not yield, so a plain pcall is safe.
  local ok, request = pcall(function()
    return Json.decode(text)
  end)
  if not ok or type(request) ~= "table" then
    writeResult(failed({ request_id = "unknown" }, "REQUEST_JSON_INVALID", "Apply request JSON could not be parsed.", true))
    Bridge.moveError(claimed)
    return
  end
  request.trigger = trigger or "bridge_request"

  -- applyRequest performs yielding catalog work, so it is protected with the SDK's
  -- yield-safe pcallWithContext rather than a plain Lua pcall. A failure here must still
  -- produce a result JSON.
  local okApply, result = LrFunctionContext.pcallWithContext("tonevyra_apply_request", function(context)
    return applyRequest(request)
  end)
  if not okApply or type(result) ~= "table" then
    result = failed(request, "LIGHTROOM_APPLY_FAILED", tostring(result), true)
  end
  writeResult(result)
  if result.status == "failed" then
    Bridge.moveError(claimed)
  else
    Bridge.moveProcessed(claimed)
  end
end

local function processPath(path, trigger)
  if activeJob then
    return
  end
  local claimed = Bridge.claim(path)
  if not claimed then
    return
  end
  activeJob = true
  -- processClaimedPath performs yielding catalog work, so it is protected with the SDK's
  -- yield-safe pcallWithContext rather than a plain Lua pcall.
  local ok, err = LrFunctionContext.pcallWithContext("tonevyra_process_path", function(context)
    processClaimedPath(claimed, trigger or "auto_bridge")
  end)
  if not ok then
    last_error = tostring(err)
  end
  activeJob = false
end

local function processClaimedExportPath(claimed, trigger)
  local text, readErr = Bridge.read(claimed)
  if not text then
    writeExportResult(exportFailed({ request_id = "unknown" }, "REQUEST_READ_FAILED", readErr or "Unable to read export request.", true))
    Bridge.moveExportError(claimed)
    return
  end

  local ok, request = pcall(function()
    return Json.decode(text)
  end)
  if not ok or type(request) ~= "table" then
    writeExportResult(exportFailed({ request_id = "unknown" }, "REQUEST_JSON_INVALID", "Export request JSON could not be parsed.", true))
    Bridge.moveExportError(claimed)
    return
  end
  request.trigger = trigger or "bridge_request"

  local okExport, result = LrFunctionContext.pcallWithContext("tonevyra_process_export_path", function(context)
    return exportRequest(request)
  end)
  if not okExport or type(result) ~= "table" then
    result = exportFailed(request, "LIGHTROOM_EXPORT_FAILED", tostring(result), true)
  end
  writeExportResult(result)
  if result.status == "failed" then
    Bridge.moveExportError(claimed)
  else
    Bridge.moveExportProcessed(claimed)
  end
end

local function processExportPath(path, trigger)
  if activeJob then
    return
  end
  local claimed = Bridge.claimExport(path)
  if not claimed then
    return
  end
  activeJob = true
  local ok, err = LrFunctionContext.pcallWithContext("tonevyra_process_export_request", function(context)
    processClaimedExportPath(claimed, trigger or "auto_bridge")
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
  start_requested = false
  running = true
  Bridge.ensureDirs()
  safeWriteWorkerStatus(true)
  while running do
    local ok, items = pcall(function()
      return Bridge.pendingRequests()
    end)
    if ok and items then
      for _, path in ipairs(items) do
        processPath(path, "auto_bridge")
      end
    else
      last_error = tostring(items)
    end
    local okExport, exportItems = pcall(function()
      return Bridge.pendingExportRequests()
    end)
    if okExport and exportItems then
      for _, path in ipairs(exportItems) do
        processExportPath(path, "auto_bridge")
      end
    else
      last_error = tostring(exportItems)
    end
    safeWriteWorkerStatus(true)
    LrTasks.sleep(2)
  end
  safeWriteWorkerStatus(false)
  return true
end

function Worker.startAsync(trigger)
  if running or start_requested then
    safeWriteWorkerStatus(running)
    return false
  end
  start_requested = true
  safeWriteWorkerStatus(false)
  LrFunctionContext.postAsyncTaskWithContext(
    "Tonevyra AI Bridge Worker",
    function(context)
      local ok, err = LrFunctionContext.pcallWithContext(
        "tonevyra_bridge_worker_start",
        function(innerContext)
          return Worker.start(innerContext)
        end
      )
      if not ok then
        running = false
        start_requested = false
        last_error = tostring(err)
        safeWriteWorkerStatus(false)
      end
    end
  )
  return true
end

function Worker.processOnePending(trigger)
  Bridge.ensureDirs()
  local ok, items = pcall(function()
    return Bridge.pendingRequests()
  end)
  if not ok then
    last_error = tostring(items)
    safeWriteWorkerStatus(running)
    return "Bridge request scan failed: " .. last_error
  end
  if not items or #items == 0 then
    safeWriteWorkerStatus(running)
    return "No pending apply request."
  end
  processPath(items[1], trigger or "diagnostic_menu")
  safeWriteWorkerStatus(running)
  return "Processed apply request: " .. tostring(items[1])
end

function Worker.processOnePendingExport(trigger)
  Bridge.ensureDirs()
  local ok, items = pcall(function()
    return Bridge.pendingExportRequests()
  end)
  if not ok then
    last_error = tostring(items)
    safeWriteWorkerStatus(running)
    return "Bridge export request scan failed: " .. last_error
  end
  if not items or #items == 0 then
    safeWriteWorkerStatus(running)
    return "No pending export request."
  end
  processExportPath(items[1], trigger or "diagnostic_menu")
  safeWriteWorkerStatus(running)
  return "Processed export request: " .. tostring(items[1])
end

function Worker.stop()
  running = false
  start_requested = false
  safeWriteWorkerStatus(false)
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
    export_request_dir = Bridge.export_request_dir,
    export_result_dir = Bridge.export_result_dir,
    last_error = last_error or "",
    worker_start_requested = tostring(start_requested),
  }
end

return Worker
