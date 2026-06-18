local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"

local Bridge = {}

Bridge.plugin_version = "t019-lightroom-apply-adapter-20260618-12"
Bridge.root = "F:\\tonevyra_ai_agent\\runtime\\bridge"
Bridge.request_dir = Bridge.root .. "\\lightroom_apply_requests"
Bridge.processing_dir = Bridge.root .. "\\lightroom_apply_processing"
Bridge.processed_dir = Bridge.root .. "\\lightroom_apply_processed"
Bridge.result_dir = Bridge.root .. "\\lightroom_apply_results"
Bridge.error_dir = Bridge.root .. "\\lightroom_apply_errors"
Bridge.live_evidence_dir = Bridge.root .. "\\lightroom_live_evidence"
Bridge.status_path = Bridge.root .. "\\lightroom_worker_status.txt"

local function ensureDir(path)
  if not LrFileUtils.exists(path) then
    LrFileUtils.createAllDirectories(path)
  end
end

function Bridge.ensureDirs()
  ensureDir(Bridge.root)
  ensureDir(Bridge.request_dir)
  ensureDir(Bridge.processing_dir)
  ensureDir(Bridge.processed_dir)
  ensureDir(Bridge.result_dir)
  ensureDir(Bridge.error_dir)
  ensureDir(Bridge.live_evidence_dir)
end

local function readAll(path)
  local handle = io.open(path, "rb")
  if not handle then
    return nil, "open_failed"
  end
  local data = handle:read("*a")
  handle:close()
  return data, nil
end

local function writeAll(path, data)
  local temp = path .. ".tmp"
  local handle = io.open(temp, "wb")
  if not handle then
    return false, "temp_open_failed"
  end
  handle:write(data)
  handle:flush()
  handle:close()
  if LrFileUtils.exists(path) then
    LrFileUtils.delete(path)
  end
  local ok = LrFileUtils.move(temp, path)
  if not ok then
    return false, "move_failed"
  end
  return true, nil
end

function Bridge.pendingRequests()
  Bridge.ensureDirs()
  local items = {}
  local iterator = LrFileUtils.files(Bridge.request_dir)
  if iterator then
    for filePath in iterator do
      if LrPathUtils.extension(filePath) == "json" then
        table.insert(items, filePath)
      end
    end
  end
  table.sort(items)
  return items
end

function Bridge.claim(path)
  Bridge.ensureDirs()
  local name = LrPathUtils.leafName(path)
  local claimed = LrPathUtils.child(Bridge.processing_dir, name)
  if LrFileUtils.exists(claimed) then
    LrFileUtils.delete(claimed)
  end
  local ok = LrFileUtils.move(path, claimed)
  if ok then
    return claimed
  end
  return nil
end

function Bridge.read(path)
  return readAll(path)
end

function Bridge.writeResult(requestId, data)
  Bridge.ensureDirs()
  local path = LrPathUtils.child(Bridge.result_dir, requestId .. ".json")
  return writeAll(path, data)
end

function Bridge.writeEvidence(requestId, data)
  Bridge.ensureDirs()
  local path = LrPathUtils.child(Bridge.live_evidence_dir, requestId .. ".json")
  return writeAll(path, data)
end

function Bridge.writeWorkerStatus(isRunning, lastError)
  Bridge.ensureDirs()
  local data = table.concat({
    "worker_running=" .. tostring(isRunning),
    "plugin_version=" .. Bridge.plugin_version,
    "updated_at=" .. os.date("!%Y-%m-%dT%H:%M:%SZ"),
    "request_dir=" .. Bridge.request_dir,
    "result_dir=" .. Bridge.result_dir,
    "last_error=" .. tostring(lastError or ""),
    "",
  }, "\n")
  return writeAll(Bridge.status_path, data)
end

function Bridge.readWorkerStatus()
  Bridge.ensureDirs()
  local data = readAll(Bridge.status_path)
  if not data then
    return nil
  end
  local status = {}
  for line in string.gmatch(data, "([^\n]+)") do
    local key, value = string.match(line, "^([^=]+)=(.*)$")
    if key then
      status[key] = value
    end
  end
  status.request_dir = status.request_dir or Bridge.request_dir
  status.result_dir = status.result_dir or Bridge.result_dir
  status.last_error = status.last_error or ""
  return status
end

function Bridge.moveError(path)
  Bridge.ensureDirs()
  local name = LrPathUtils.leafName(path)
  local target = LrPathUtils.child(Bridge.error_dir, name)
  if LrFileUtils.exists(target) then
    LrFileUtils.delete(target)
  end
  LrFileUtils.move(path, target)
end

function Bridge.moveProcessed(path)
  Bridge.ensureDirs()
  local name = LrPathUtils.leafName(path)
  local target = LrPathUtils.child(Bridge.processed_dir, name)
  if LrFileUtils.exists(target) then
    LrFileUtils.delete(target)
  end
  LrFileUtils.move(path, target)
end

return Bridge
