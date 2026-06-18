local LrDialogs = import "LrDialogs"

local Worker = require "Worker"

local status = Worker.status()

LrDialogs.message(
  "Tonevyra AI",
  "Bridge worker: " .. status.worker_running ..
    "\nPlugin version: " .. (status.plugin_version or "unknown") ..
    "\nUpdated: " .. (status.updated_at or "unknown") ..
    "\nRequests: " .. status.request_dir ..
    "\nResults: " .. status.result_dir ..
    "\nLast error: " .. (status.last_error or ""),
  "info"
)
