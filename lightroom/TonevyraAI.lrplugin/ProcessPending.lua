local LrDialogs = import "LrDialogs"
local LrTasks = import "LrTasks"

local Worker = require "Worker"

LrTasks.startAsyncTask(function()
  local ok, result = pcall(function()
    return Worker.processOnePending("manual_menu")
  end)
  if ok then
    LrDialogs.message("Tonevyra AI", result or "No pending apply request.", "info")
  else
    LrDialogs.message("Tonevyra AI", tostring(result), "critical")
  end
end)
