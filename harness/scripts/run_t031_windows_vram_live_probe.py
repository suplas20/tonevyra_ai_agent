#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
out=Path('runtime/evidence/t031/windows_vram_probe.json'); out.parent.mkdir(parents=True,exist_ok=True)
if sys.platform!='win32':
    data={'ticket':'T-031','os':sys.platform,'strict_completion':False,'blocked_reasons':['BLOCKED_WINDOWS_VRAM_EVIDENCE_MISSING']}
else:
    try:
        raw=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True,timeout=15)
        rows=[x.strip() for x in raw.splitlines() if x.strip()]
        data={'ticket':'T-031','os':'windows','nvidia_rows':rows,'strict_completion':False,'blocked_reasons':['MANUAL_WORKER_IDLE_UNLOAD_SEQUENCE_REQUIRED']}
    except Exception as e:
        data={'ticket':'T-031','os':'windows','strict_completion':False,'blocked_reasons':['NVIDIA_SMI_PROBE_FAILED'],'error':str(e)}
out.write_text(json.dumps(data,indent=2),encoding='utf-8'); print(json.dumps(data,indent=2))
