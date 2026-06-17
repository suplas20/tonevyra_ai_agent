-- Tonevyra AI Lightroom Classic Plugin Scaffold
-- Folder-driven automation entrypoint.
-- Lua plugin = thin Lightroom apply worker only. No AI, no database, no network calls.

local LrTasks = import "LrTasks"
local Worker = require "Worker"

LrTasks.startAsyncTask(function()
  Worker.start()
end)
