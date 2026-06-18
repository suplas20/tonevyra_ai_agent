return {
  LrSdkVersion = 6.0,
  LrSdkMinimumVersion = 6.0,
  LrToolkitIdentifier = "com.tonevyra.ai.agent",
  LrPluginName = "Tonevyra AI",

  LrInitPlugin = "Main.lua",
  LrShutdownPlugin = "Shutdown.lua",

  LrLibraryMenuItems = {
    {
      title = "Tonevyra Process Pending Apply Request",
      file = "ProcessPending.lua",
    },
    {
      title = "Tonevyra Bridge Status",
      file = "Status.lua",
    },
  },
}
