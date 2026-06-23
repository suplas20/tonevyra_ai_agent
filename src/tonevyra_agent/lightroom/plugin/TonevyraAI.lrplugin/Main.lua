local LrApplication = import "LrApplication"
local LrExportSession = import "LrExportSession"
local LrFileUtils = import "LrFileUtils"
local LrLogger = import "LrLogger"
local LrPathUtils = import "LrPathUtils"
local LrPrefs = import "LrPrefs"
local LrTasks = import "LrTasks"

local logger = LrLogger("TonevyraAI")
logger:enable("logfile")

local POLL_INTERVAL_SECONDS = 2
local ERROR_LIGHTROOM_REQUEST_FAILED = "LIGHTROOM_REQUEST_FAILED"
local ERROR_LIGHTROOM_EXPORT_FAILED = "LIGHTROOM_EXPORT_FAILED"

local prefs = LrPrefs.prefsForPlugin()

local function pathExists(path)
  return path ~= nil and LrFileUtils.exists(path) == "file"
end

local function directoryExists(path)
  return path ~= nil and LrFileUtils.exists(path) == "directory"
end

local function ensureDirectory(path)
  if not directoryExists(path) then
    LrFileUtils.createAllDirectories(path)
  end
end

local function pluginDefaultBridgeDir()
  local path = _PLUGIN.path
  for _ = 1, 5 do
    path = LrPathUtils.parent(path)
  end
  return LrPathUtils.child(LrPathUtils.child(path, "runtime"), "bridge")
end

local function bridgeDir()
  if prefs.bridgeDir ~= nil and prefs.bridgeDir ~= "" then
    return prefs.bridgeDir
  end
  return pluginDefaultBridgeDir()
end

local function bridgeChild(name)
  return LrPathUtils.child(bridgeDir(), name)
end

local function requestDir()
  return bridgeChild("requests")
end

local function processingDir()
  return bridgeChild("processing")
end

local function responseDir()
  return bridgeChild("responses")
end

local function errorDir()
  return bridgeChild("errors")
end

local function ensureBridgeDirs()
  ensureDirectory(requestDir())
  ensureDirectory(processingDir())
  ensureDirectory(responseDir())
  ensureDirectory(errorDir())
end

local function readText(path)
  local handle = io.open(path, "rb")
  if handle == nil then
    error("failed to open file: " .. tostring(path))
  end
  local text = handle:read("*a")
  handle:close()
  return text
end

local function writeTextAtomic(path, text)
  ensureDirectory(LrPathUtils.parent(path))
  local tempPath = path .. ".tmp"
  local handle = io.open(tempPath, "wb")
  if handle == nil then
    error("failed to write file: " .. tostring(tempPath))
  end
  handle:write(text)
  handle:flush()
  handle:close()
  if pathExists(path) then
    LrFileUtils.delete(path)
  end
  LrFileUtils.move(tempPath, path)
end

local function jsonEscape(value)
  value = tostring(value or "")
  value = value:gsub("\\", "\\\\")
  value = value:gsub('"', '\\"')
  value = value:gsub("\r", "\\r")
  value = value:gsub("\n", "\\n")
  value = value:gsub("\t", "\\t")
  return value
end

local function encodeJsonObject(payload)
  local fields = {}
  for key, value in pairs(payload) do
    if value ~= nil then
      if type(value) == "number" then
        table.insert(fields, '"' .. jsonEscape(key) .. '":' .. tostring(value))
      else
        table.insert(fields, '"' .. jsonEscape(key) .. '":"' .. jsonEscape(value) .. '"')
      end
    end
  end
  table.sort(fields)
  return "{\n  " .. table.concat(fields, ",\n  ") .. "\n}\n"
end

local function unescapeJsonString(value)
  value = value:gsub('\\"', '"')
  value = value:gsub("\\\\", "\\")
  value = value:gsub("\\/", "/")
  value = value:gsub("\\r", "\r")
  value = value:gsub("\\n", "\n")
  value = value:gsub("\\t", "\t")
  return value
end

local function jsonStringField(text, key)
  local pattern = '"' .. key .. '"%s*:%s*"(.-)"'
  local value = text:match(pattern)
  if value == nil then
    return nil
  end
  return unescapeJsonString(value)
end

local function jsonObjectBody(text, key)
  return text:match('"' .. key .. '"%s*:%s*{(.-)}')
end

local function parseAdjustments(text)
  local adjustments = {}
  local body = jsonObjectBody(text, "adjustments")
  if body == nil then
    return adjustments
  end
  for key, value in body:gmatch('"([%w_]+)"%s*:%s*([%-%.%d]+)') do
    adjustments[key] = tonumber(value)
  end
  return adjustments
end

local function parseRequest(path)
  local text = readText(path)
  local request = {
    schema_version = jsonStringField(text, "schema_version") or "1.0",
    request_id = jsonStringField(text, "request_id"),
    task_id = jsonStringField(text, "task_id"),
    command = jsonStringField(text, "command") or "APPLY_ADJUSTMENTS_AND_EXPORT",
    source_path = jsonStringField(text, "source_path"),
    export_path = jsonStringField(text, "export_path"),
    correction_plan_path = jsonStringField(text, "correction_plan_path"),
    adjustments = parseAdjustments(text),
  }
  if request.request_id == nil or request.task_id == nil then
    error("request_id and task_id are required")
  end
  return request
end

local function responsePath(request)
  return LrPathUtils.child(responseDir(), request.request_id .. ".json")
end

local function writeSuccess(request, exportPath)
  writeTextAtomic(responsePath(request), encodeJsonObject({
    schema_version = "1.0",
    request_id = request.request_id,
    task_id = request.task_id,
    command = request.command,
    status = "success",
    export_path = exportPath,
  }))
end

local function writeFailure(request, errorCode, message)
  local path = responsePath(request)
  if request.request_id == nil then
    path = LrPathUtils.child(errorDir(), "invalid_request.error.json")
  end
  writeTextAtomic(path, encodeJsonObject({
    schema_version = "1.0",
    request_id = request.request_id or "invalid_request",
    task_id = request.task_id or "invalid_request",
    command = request.command,
    status = "failed",
    error_code = errorCode,
    error_message = message,
  }))
end

local DEVELOP_SETTING_KEYS = {
  exposure = "Exposure2012",
  contrast = "Contrast2012",
  highlights = "Highlights2012",
  shadows = "Shadows2012",
  whites = "Whites2012",
  blacks = "Blacks2012",
  tint = "Tint",
  vibrance = "Vibrance",
  saturation = "Saturation",
  texture = "Texture",
  clarity = "Clarity2012",
  dehaze = "Dehaze",
  noise_reduction = "LuminanceSmoothing",
  sharpening = "Sharpness",
}

local function clamp(value, low, high)
  if value < low then
    return low
  end
  if value > high then
    return high
  end
  return value
end

local function buildDevelopSettings(photo, adjustments)
  local developSettings = {}
  for tonevyraKey, lightroomKey in pairs(DEVELOP_SETTING_KEYS) do
    if adjustments[tonevyraKey] ~= nil then
      developSettings[lightroomKey] = adjustments[tonevyraKey]
    end
  end
  if adjustments.temperature_delta ~= nil then
    local current = photo:getDevelopSettings()
    local baseTemperature = tonumber(current and current.Temperature)
    local delta = tonumber(adjustments.temperature_delta)
    if baseTemperature ~= nil and delta ~= nil then
      developSettings.Temperature = clamp(baseTemperature + clamp(delta, -2000, 2000), 2500, 50000)
    end
  end
  return developSettings
end

local function findOrImportPhoto(catalog, sourcePath)
  local photos = catalog:findPhotos { searchDesc = sourcePath }
  if photos ~= nil then
    for _, photo in ipairs(photos) do
      if photo:getRawMetadata("path") == sourcePath then
        return photo
      end
    end
  end

  local importedPhoto = nil
  catalog:withWriteAccessDo("Tonevyra AI Import Photo", function()
    importedPhoto = catalog:addPhoto(sourcePath)
  end)
  return importedPhoto
end

local function applyDevelopSettings(catalog, photo, adjustments)
  catalog:withWriteAccessDo("Tonevyra AI Apply Adjustments", function()
    local developSettings = buildDevelopSettings(photo, adjustments)
    photo:applyDevelopSettings(developSettings)
  end)
end

local function exportPhoto(photo, exportPath)
  ensureDirectory(LrPathUtils.parent(exportPath))
  local exportFolder = LrPathUtils.parent(exportPath)
  local exportName = LrPathUtils.removeExtension(LrPathUtils.leafName(exportPath))
  local exportSession = LrExportSession {
    photosToExport = { photo },
    exportSettings = {
      LR_export_destinationType = "specificFolder",
      LR_export_destinationPathPrefix = exportFolder,
      LR_export_useSubfolder = false,
      LR_format = "JPEG",
      LR_jpeg_quality = 0.92,
      LR_renamingTokensOn = true,
      LR_tokens = exportName,
      LR_collisionHandling = "overwrite",
    },
  }
  exportSession:doExportOnCurrentTask()
end

local function handleApplyAdjustmentsAndExport(request)
  if request.source_path == nil or request.export_path == nil then
    error("source_path and export_path are required")
  end
  if not pathExists(request.source_path) then
    error("source_path does not exist: " .. request.source_path)
  end

  local catalog = LrApplication.activeCatalog()
  local photo = findOrImportPhoto(catalog, request.source_path)
  if photo == nil then
    error("failed to import or find source photo")
  end

  applyDevelopSettings(catalog, photo, request.adjustments or {})
  exportPhoto(photo, request.export_path)

  if not pathExists(request.export_path) then
    error("Lightroom export completed but export_path is missing: " .. request.export_path)
  end
  writeSuccess(request, request.export_path)
end

local function processRequest(path)
  local fileName = LrPathUtils.leafName(path)
  local processingPath = LrPathUtils.child(processingDir(), fileName)
  local request = {}

  if pathExists(processingPath) then
    LrFileUtils.delete(processingPath)
  end
  LrFileUtils.move(path, processingPath)

  local ok, err = pcall(function()
    request = parseRequest(processingPath)
    if request.command == "PING" then
      writeSuccess(request, nil)
    elseif request.command == "APPLY_ADJUSTMENTS_AND_EXPORT" then
      handleApplyAdjustmentsAndExport(request)
    else
      error("unsupported Lightroom bridge command: " .. tostring(request.command))
    end
  end)

  if not ok then
    logger:error("Tonevyra AI request failed: " .. tostring(err))
    writeFailure(request, ERROR_LIGHTROOM_EXPORT_FAILED, tostring(err))
  end
end

local function processPendingRequests()
  ensureBridgeDirs()
  for path in LrFileUtils.files(requestDir()) do
    if path:match("%.json$") then
      processRequest(path)
    end
  end
end

LrTasks.startAsyncTask(function()
  logger:trace("Tonevyra AI Lightroom plugin loaded")
  ensureBridgeDirs()
  while true do
    local ok, err = pcall(processPendingRequests)
    if not ok then
      logger:error("Tonevyra AI bridge poll failed: " .. tostring(err))
    end
    LrTasks.sleep(POLL_INTERVAL_SECONDS)
  end
end)
