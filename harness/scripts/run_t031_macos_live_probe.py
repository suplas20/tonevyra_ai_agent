#!/usr/bin/env python3
import json, platform, sys
from pathlib import Path
out=Path('runtime/evidence/t031/macos_live_probe.json'); out.parent.mkdir(parents=True,exist_ok=True)
if sys.platform!='darwin':
    data={'ticket':'T-031','os':sys.platform,'strict_completion':False,'blocked_reasons':['BLOCKED_MACOS_LIVE_EVIDENCE_MISSING']}
else:
    data={'ticket':'T-031','os':'macos','architecture':platform.machine(),'strict_completion':False,'blocked_reasons':['MANUAL_MENU_BAR_FSEVENTS_MPS_LIGHTROOM_EVIDENCE_REQUIRED']}
out.write_text(json.dumps(data,indent=2),encoding='utf-8'); print(json.dumps(data,indent=2))
