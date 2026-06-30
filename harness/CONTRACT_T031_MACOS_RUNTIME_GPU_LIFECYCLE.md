# T-031 macOS Runtime and GPU Memory Lifecycle Harness Contract

- Core business logic remains platform-neutral.
- Windows and macOS differences are isolated behind explicit adapters.
- macOS production target is Apple Silicon arm64; Rosetta is not a completion path.
- The always-on Shell/Watcher must not import or load the model runtime.
- At most one Inference Worker may exist per user runtime.
- The Inference Worker starts lazily when durable work is available.
- Empty queue enters a bounded idle grace period.
- Grace expiry terminates the Inference Worker process and releases its GPU context.
- `empty_cache()` alone is not acceptable unload evidence.
- MPS fallback to CPU is explicit, observable, and disabled by default.
- FSEvents notifications trigger bounded rescans; they do not directly equal jobs.
- PostgreSQL remains the durable queue and recovery source.
- Real macOS and real Windows VRAM evidence are required for strict completion.
- T-019 through T-030 regressions remain mandatory.
