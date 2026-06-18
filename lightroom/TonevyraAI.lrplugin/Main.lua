local LrFunctionContext = import "LrFunctionContext"

local Worker = require "Worker"

LrFunctionContext.callWithContext("Tonevyra AI Apply Adapter", function(context)
  Worker.start(context)
end)
