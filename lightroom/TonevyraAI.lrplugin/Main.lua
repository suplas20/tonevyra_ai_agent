local LrTasks = import "LrTasks"

local Worker = require "Worker"

LrTasks.startAsyncTask(function()
  Worker.start()
end)
