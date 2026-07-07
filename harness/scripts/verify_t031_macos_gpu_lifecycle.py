#!/usr/bin/env python3
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
required=[
'.docs/t031/T-031_macOS_Apple_Silicon_Runtime_and_Idle_VRAM_Work_Order.md',
'.docs/t031/T-031_Implementation_Specification.md',
'harness/CONTRACT_T031_MACOS_RUNTIME_GPU_LIFECYCLE.md',
'harness/schemas/t031_runtime_evidence.schema.json',
'harness/schemas/t031_macos_live_evidence.schema.json',
'harness/schemas/t031_windows_vram_live_evidence.schema.json',
'skills/macos-apple-silicon-runtime/SKILL.md',
'skills/inference-worker-memory-lifecycle/SKILL.md']
missing=[x for x in required if not (ROOT/x).is_file()]
skills=sorted(p.parent.name for p in (ROOT/'skills').glob('*/SKILL.md'))
errors=[]
if missing: errors.append('missing:'+','.join(missing))
if len(skills)<47: errors.append(f'skill_count={len(skills)} expected_at_least=47')
if 'macos-apple-silicon-runtime' not in skills or 'inference-worker-memory-lifecycle' not in skills: errors.append('new_skills_missing')
ref=ROOT/'runtime/evidence/t031/reference_runtime_evidence.json'
if ref.exists():
    data=json.loads(ref.read_text())
    wl=data.get('worker_lifecycle',{})
    if not all([wl.get('lazy_start'), wl.get('idle_unload'), wl.get('process_exit_verified'), wl.get('max_workers')==1]): errors.append('reference_lifecycle_failed')
print(json.dumps({'ticket':'T-031','ok':not errors,'errors':errors,'skill_count':len(skills)},indent=2))
sys.exit(1 if errors else 0)
