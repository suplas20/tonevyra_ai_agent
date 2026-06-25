local Worker = require "Worker"

-- Lightroom loads this file via LrInitPlugin when the plugin is enabled.
-- The worker must be active whenever Lightroom Classic is running; menu items
-- are diagnostic-only and must not be required to start bridge processing.
Worker.startAsync("lightroom_init")
