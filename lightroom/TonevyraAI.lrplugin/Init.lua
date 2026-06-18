local LrFunctionContext = import "LrFunctionContext"

local Worker = require "Worker"

LrFunctionContext.postAsyncTaskWithContext("Tonevyra AI Bridge Worker", function(context)
  Worker.start(context)
end)
