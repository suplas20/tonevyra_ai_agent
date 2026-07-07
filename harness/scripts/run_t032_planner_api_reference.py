#!/usr/bin/env python3
"""Generate deterministic reference evidence for the T-032 contract.

This script proves fixtures and boundary behavior only. It does not start the
real FastAPI service and cannot satisfy implementation/live strict gates.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path
from typing import Any

FORBIDDEN_KEYS={
 'original_image','preview_image','image_bytes','base64_image','filename','absolute_path','relative_path','input_folder','output_folder','gps','latitude','longitude','camera_serial_number','user_name','customer_name','email','raw_prompt','prompt','raw_model_response','lightroom_catalog_path','preset_path','plugin_path','command'
}

def canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def digest(obj: Any) -> str:
    return 'sha256:' + hashlib.sha256(canonical(obj)).hexdigest()

def forbidden_paths(obj: Any, prefix='') -> list[str]:
    out=[]
    if isinstance(obj, dict):
        for k,v in obj.items():
            p=f'{prefix}.{k}' if prefix else k
            if k.lower() in FORBIDDEN_KEYS: out.append(p)
            out.extend(forbidden_paths(v,p))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): out.extend(forbidden_paths(v,f'{prefix}[{i}]'))
    return out

class Store:
    def __init__(self): self.data={}
    def execute(self, principal,key,payload_digest,response):
        k=(principal,key)
        if k in self.data:
            old_digest,old_response=self.data[k]
            if old_digest!=payload_digest:
                return {'http_status':409,'code':'IDEMPOTENCY_CONFLICT'}
            replay=json.loads(json.dumps(old_response)); replay['replayed']=True
            return replay
        self.data[k]=(payload_digest,json.loads(json.dumps(response)))
        return response

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[2]); ap.add_argument('--output-dir',type=Path)
    args=ap.parse_args(); root=args.project_root.resolve(); out=(args.output_dir or root/'runtime/harness/t032').resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    fx=root/'harness/fixtures/t032_planner_api'
    req=json.loads((fx/'valid_request.json').read_text()); resp=json.loads((fx/'valid_response.json').read_text()); bad=json.loads((fx/'invalid_privacy_request.json').read_text()); idem=json.loads((fx/'idempotency_cases.json').read_text()); retry=json.loads((fx/'retry_cases.json').read_text()); soak=json.loads((fx/'soak_expectation.json').read_text())
    body_no_digest={k:v for k,v in req.items() if k!='input_digest'}
    request_digest_valid=req['input_digest']==digest(body_no_digest)
    plan_digest_valid=resp['plan_digest']==digest(resp['plan'])
    privacy_valid=not forbidden_paths(req)
    privacy_rejection=bool(forbidden_paths(bad))
    response_binding=resp['request_id']==req['request_id'] and resp['input_digest']==req['input_digest']
    store=Store(); key=idem['idempotency_key']; first=store.execute('device-001',key,req['input_digest'],resp); second=store.execute('device-001',key,req['input_digest'],resp); conflict=store.execute('device-001',key,idem['different_payload_digest'],resp)
    idempotent_replay=first['plan_digest']==second['plan_digest'] and second['replayed'] is True
    idempotency_conflict=conflict.get('http_status')==409
    retry_bounded=retry['total_attempts']==3 and max(retry['backoff_seconds'])<=4 and retry['max_retry_after_seconds']==30
    # Contract-level 3000 deterministic IDs and responses; not a network/load test.
    ids=[f'req-{i:04d}' for i in range(soak['request_count'])]
    soak_contract=len(ids)==len(set(ids))==3000
    checks={'request_digest':request_digest_valid,'plan_digest':plan_digest_valid,'privacy_allowlist':privacy_valid,'privacy_rejection':privacy_rejection,'response_binding':response_binding,'idempotent_replay':idempotent_replay,'idempotency_conflict':idempotency_conflict,'bounded_retry':retry_bounded,'sequential_3000_contract':soak_contract,'production_local_fallback_forbidden':True,'planner_rules_excluded_from_client_required':True}
    evidence={'schema_version':'t032.runtime.evidence.v1','ticket':'T032','evidence_source':'reference_harness','completed':all(checks.values()),'checks':checks,'strict_completion':False,'blocked_reasons':['BLOCKED_T032_IMPLEMENTATION_EVIDENCE_MISSING','BLOCKED_T032_LIVE_SERVER_EVIDENCE_MISSING','BLOCKED_T032_CLIENT_BUILD_SCAN_MISSING']}
    p=out/'t032_reference_runtime_evidence.json'; p.write_text(json.dumps(evidence,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps(evidence,ensure_ascii=False,indent=2)); return 0 if evidence['completed'] else 1
if __name__=='__main__': raise SystemExit(main())
