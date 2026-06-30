local LrFunctionContext = import "LrFunctionContext"
local LrDialogs = import "LrDialogs"

local Worker = require "Worker"

LrFunctionContext.postAsyncTaskWithContext(
  "Tonevyra Process Pending Mask Request",
  function(context)
    local result = Worker.processOnePendingMask("diagnostic_menu")
    LrDialogs.message("Tonevyra AI", tostring(result), "info")
  end
)
