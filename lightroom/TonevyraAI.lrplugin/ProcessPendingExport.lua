local LrDialogs = import "LrDialogs"
local LrTasks = import "LrTasks"

local Worker = require "Worker"

-- Diagnostic-only: process one existing bridge export request and report the result.
-- The formal product path is Worker.start() automatic bridge processing.
LrTasks.startAsyncTask(function()
  local ok, result = pcall(function()
    return Worker.processOnePendingExport("diagnostic_menu")
  end)
  if ok then
    LrDialogs.message("Tonevyra AI", result or "No pending export request.", "info")
  else
    LrDialogs.message("Tonevyra AI", tostring(result), "critical")
  end
end)
