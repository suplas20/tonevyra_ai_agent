local LrDialogs = import "LrDialogs"
local LrFunctionContext = import "LrFunctionContext"
local LrTasks = import "LrTasks"

local Worker = require "Worker"

-- Diagnostic-only: process one existing bridge apply request and report the result.
-- All bridge processing runs inside an async task. The underlying catalog work yields,
-- so the protected call uses the SDK's yield-safe pcallWithContext, never a plain Lua
-- pcall (which would raise "Yielding is not allowed within a C or metamethod call").
LrTasks.startAsyncTask(function()
  local ok, result = LrFunctionContext.pcallWithContext("tonevyra_diagnostic_process_pending", function(context)
    return Worker.processOnePending("diagnostic_menu")
  end)
  if ok then
    LrDialogs.message("Tonevyra AI", result or "No pending apply request.", "info")
  else
    LrDialogs.message("Tonevyra AI", tostring(result), "critical")
  end
end)
