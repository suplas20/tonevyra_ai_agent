#!/usr/bin/env python3
"""Static/reference/strict evidence verifier for T-032."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any

TICKET='T032'; EXPECTED_SKILLS=51
REQUIRED_SKILLS={'planner-api-contract','planner-api-client','planner-api-service','planner-api-security'}
REQUIRED_FILES=[
'.docs/t032/T-032_Planner_Engine_API_Separation_Work_Order.md','.docs/t032/T-032_Implementation_Specification.md','.docs/t032/T-032_API_Contract.md','.docs/t032/T-032_Server_Deployment_Guide.md','.docs/t032/T-032_Live_Test_Checklist.md','.docs/t032/T-032_Codex_Prompt.md',
'harness/CONTRACT_T032_PLANNER_API_SEPARATION.md','harness/HARNESS_ENV_T032_PLANNER_API.example','harness/T032_PLANNER_API_UPDATE_MANIFEST.json',
'harness/schemas/t032_planner_request.schema.json','harness/schemas/t032_planner_response.schema.json','harness/schemas/t032_planner_error.schema.json','harness/schemas/t032_runtime_evidence.schema.json','harness/schemas/t032_live_server_evidence.schema.json','harness/schemas/t032_client_build_scan.schema.json','harness/schemas/t032_sequential_soak.schema.json',
'harness/fixtures/t032_planner_api/valid_request.json','harness/fixtures/t032_planner_api/valid_response.json','harness/fixtures/t032_planner_api/invalid_privacy_request.json','harness/fixtures/t032_planner_api/idempotency_cases.json','harness/fixtures/t032_planner_api/retry_cases.json','harness/fixtures/t032_planner_api/version_mismatch_response.json','harness/fixtures/t032_planner_api/soak_expectation.json',
'harness/scripts/run_t032_planner_api_reference.py','harness/scripts/run_t032_planner_api_live_probe.py','skills/T032_SKILL_INVENTORY.json']
FORBIDDEN_REQUEST_KEYS={'original_image','preview_image','image_bytes','base64_image','filename','absolute_path','relative_path','input_folder','output_folder','gps','latitude','longitude','camera_serial_number','user_name','customer_name','email','raw_prompt','prompt','raw_model_response','lightroom_catalog_path','preset_path','plugin_path','command'}

def load(p:Path)->Any: return json.loads(p.read_text(encoding='utf-8'))
def walk_keys(obj:Any):
    if isinstance(obj,dict):
        for k,v in obj.items(): yield k; yield from walk_keys(v)
    elif isinstance(obj,list):
        for v in obj: yield from walk_keys(v)

def validate_static(root:Path)->list[str]:
    f=[]
    missing=[x for x in REQUIRED_FILES if not (root/x).is_file()]
    if missing: f.extend('missing:'+x for x in missing)
    skills=sorted(p.parent.name for p in (root/'skills').glob('*/SKILL.md'))
    if len(skills)!=EXPECTED_SKILLS: f.append(f'skill_count={len(skills)} expected={EXPECTED_SKILLS}')
    for s in REQUIRED_SKILLS:
        if s not in skills: f.append('missing_skill:'+s)
    inv=root/'skills/T032_SKILL_INVENTORY.json'
    if inv.exists():
        d=load(inv)
        if d.get('expected_total_skill_count')!=EXPECTED_SKILLS: f.append('inventory total mismatch')
        if sorted(d.get('all_skills',[]))!=skills: f.append('inventory skill list mismatch')
    reqp=root/'harness/fixtures/t032_planner_api/valid_request.json'
    if reqp.exists():
        req=load(reqp); bad=sorted({k.lower() for k in walk_keys(req)} & FORBIDDEN_REQUEST_KEYS)
        if bad: f.append('valid request contains forbidden keys:'+','.join(bad))
    agents=(root/'AGENTS.md').read_text(encoding='utf-8')
    for needle in ['T-032 Planner API Separation Policy','production local Planner fallback is forbidden','51']:
        if needle not in agents: f.append('AGENTS missing T032 rule:'+needle)
    claude=(root/'CLAUDE.md').read_text(encoding='utf-8')
    if 'Required reading for T-032' not in claude: f.append('CLAUDE missing T032 reading section')
    return f

def validate_runtime(path:Path, strict:bool)->list[str]:
    f=[]; d=load(path)
    if d.get('schema_version')!='t032.runtime.evidence.v1': f.append('runtime schema mismatch')
    if d.get('ticket')!=TICKET: f.append('runtime ticket mismatch')
    if d.get('completed') is not True: f.append('runtime not completed')
    checks=d.get('checks',{})
    for k in ['request_digest','plan_digest','privacy_allowlist','privacy_rejection','response_binding','idempotent_replay','idempotency_conflict','bounded_retry','sequential_3000_contract','production_local_fallback_forbidden','planner_rules_excluded_from_client_required']:
        if checks.get(k) is not True: f.append('runtime check failed:'+k)
    if strict and d.get('evidence_source')!='implementation': f.append('strict runtime evidence must be implementation')
    return f

def validate_live(path:Path)->list[str]:
    f=[]; d=load(path)
    required=['https_verified','unauthorized_rejected','authorized_plan_valid','idempotent_replay','idempotency_conflict_rejected','secret_redaction_verified']
    if d.get('schema_version')!='t032.live_server_evidence.v1' or d.get('ticket')!=TICKET: f.append('live schema/ticket mismatch')
    for k in required:
        if d.get(k) is not True: f.append('live field must be true:'+k)
    if not str(d.get('base_url','')).startswith('https://'): f.append('live base_url must use https')
    if not d.get('implementation_build') or d.get('implementation_build')=='<fill>': f.append('live implementation_build missing')
    return f

def validate_build(path:Path)->list[str]:
    d=load(path); f=[]
    if d.get('schema_version')!='t032.client_build_scan.v1' or d.get('ticket')!=TICKET: f.append('build scan schema/ticket mismatch')
    for k in ['planner_rules_absent','local_fallback_absent','mock_test_only']:
        if d.get(k) is not True: f.append('build scan field must be true:'+k)
    if not d.get('build_sha256') or d.get('build_sha256')=='<fill>': f.append('build_sha256 missing')
    return f

def validate_soak(path:Path)->list[str]:
    d=load(path); f=[]
    if d.get('schema_version')!='t032.sequential_soak.v1' or d.get('ticket')!=TICKET: f.append('soak schema/ticket mismatch')
    expected={'request_count':3000,'success_count':3000,'missing_count':0,'duplicate_response_ids':0,'duplicate_external_effects':0,'server_crashes':0}
    for k,v in expected.items():
        if d.get(k)!=v: f.append(f'soak {k}={d.get(k)!r} expected={v!r}')
    return f

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[2]); ap.add_argument('--runtime-evidence',type=Path); ap.add_argument('--live-evidence',type=Path); ap.add_argument('--client-build-scan',type=Path); ap.add_argument('--soak-evidence',type=Path); ap.add_argument('--strict',action='store_true'); a=ap.parse_args(); root=a.project_root.resolve()
    failures=validate_static(root)
    if a.runtime_evidence: failures+=validate_runtime(a.runtime_evidence.resolve(),a.strict)
    elif a.strict: failures.append('strict requires --runtime-evidence')
    if a.live_evidence: failures+=validate_live(a.live_evidence.resolve())
    elif a.strict: failures.append('strict requires --live-evidence')
    if a.client_build_scan: failures+=validate_build(a.client_build_scan.resolve())
    elif a.strict: failures.append('strict requires --client-build-scan')
    if a.soak_evidence: failures+=validate_soak(a.soak_evidence.resolve())
    elif a.strict: failures.append('strict requires --soak-evidence')
    if failures:
        print('FAIL: T032'); [print('- '+x) for x in failures]; return 1
    print('PASS: T032 static contract, skills, schemas, and fixtures')
    if a.runtime_evidence: print('PASS: T032 runtime evidence')
    if a.live_evidence: print('PASS: T032 live HTTPS evidence')
    if a.client_build_scan: print('PASS: T032 production client build scan')
    if a.soak_evidence: print('PASS: T032 3000 sequential soak evidence')
    if a.strict: print('PASS: T032 strict completion gate')
    return 0
if __name__=='__main__': sys.exit(main())
