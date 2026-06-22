return {
  LrSdkVersion = 6.0,
  LrSdkMinimumVersion = 6.0,
  LrToolkitIdentifier = "com.tonevyra.ai.agent",
  LrPluginName = "Tonevyra AI",

  LrInitPlugin = "Main.lua",
  LrShutdownPlugin = "Shutdown.lua",

  LrLibraryMenuItems = {
    {
      title = "Tonevyra Diagnostics Process Pending Apply Request",
      file = "ProcessPending.lua",
    },
    {
      title = "Tonevyra Diagnostics Process Pending Export Request",
      file = "ProcessPendingExport.lua",
    },
    {
      title = "Tonevyra Bridge Status",
      file = "Status.lua",
    },
  },
}
