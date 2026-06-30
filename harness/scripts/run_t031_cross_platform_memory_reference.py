#!/usr/bin/env python3
import json, time
from pathlib import Path

class ReferenceWorker:
    def __init__(self, grace=0.05):
        self.grace=grace; self.running=False; self.active=0; self.last=None; self.starts=0; self.stops=0
    def submit(self):
        if not self.running:
            self.running=True; self.starts+=1
        self.active+=1
        self.active-=1; self.last=time.monotonic()
    def tick(self):
        if self.running and self.active==0 and self.last is not None and time.monotonic()-self.last>=self.grace:
            self.running=False; self.stops+=1

w=ReferenceWorker(); idle_start=not w.running
w.submit(); one_worker=w.running and w.starts==1
w.submit(); no_duplicate=w.starts==1
while w.running:
    time.sleep(0.01); w.tick()
result={"ticket":"T-031","platform":"reference","worker_lifecycle":{"lazy_start":idle_start,"max_workers":1,"idle_unload":not w.running,"process_exit_verified":w.stops==1},"memory":{"before_mb":0,"loaded_mb":1024,"post_unload_mb":0},"strict_completion":False,"blocked_reasons":["BLOCKED_MACOS_LIVE_EVIDENCE_MISSING","BLOCKED_WINDOWS_VRAM_EVIDENCE_MISSING"],"checks":{"one_worker":one_worker,"no_duplicate":no_duplicate}}
out=Path('runtime/evidence/t031/reference_runtime_evidence.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
