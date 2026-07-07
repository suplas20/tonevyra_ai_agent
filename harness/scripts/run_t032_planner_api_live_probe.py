#!/usr/bin/env python3
"""Minimal HTTPS live probe for an implemented T-032 Planner Service.

The API key is read from an environment variable and is never printed or saved.
This probe performs liveness/readiness/version, unauthorized rejection, one
valid call, same-key replay, and same-key/different-payload conflict.
"""
from __future__ import annotations
import argparse, hashlib, json, os, ssl, sys, urllib.error, urllib.request, uuid
from pathlib import Path
from typing import Any

def canonical(o:Any)->bytes: return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(o:Any)->str: return 'sha256:'+hashlib.sha256(canonical(o)).hexdigest()
def call(url:str,method='GET',body=None,headers=None,timeout=15):
    data=None if body is None else canonical(body)
    req=urllib.request.Request(url,data=data,method=method,headers=headers or {})
    try:
        with urllib.request.urlopen(req,timeout=timeout,context=ssl.create_default_context()) as r:
            return r.status,json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try: payload=json.loads(e.read().decode() or '{}')
        except Exception: payload={}
        return e.code,payload

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',required=True); ap.add_argument('--api-key-env',default='TONEVYRA_PLANNER_API_KEY'); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--implementation-build',default='<fill>'); a=ap.parse_args()
    if not a.base_url.startswith('https://'):
        print('ERROR: HTTPS base URL required',file=sys.stderr); return 2
    key=os.environ.get(a.api_key_env)
    if not key:
        print(f'ERROR: environment variable {a.api_key_env} is not set',file=sys.stderr); return 2
    base=a.base_url.rstrip('/'); live=call(base+'/health/live')[0]==200; ready=call(base+'/health/ready')[0]==200; version_status,version=call(base+'/api/v1/version')
    rid=str(uuid.uuid4()); body0={'schema_version':'t032.planner.request.v1','request_id':rid,'client':{'agent_version':'probe','platform':'windows','device_id_hash':'sha256:'+'1'*64},'image_context':{'width':100,'height':100,'orientation':1},'analysis':{'analysis_schema_version':'vision.analysis.v1','scene_type':'test','confidence':1.0},'preferences':{'correction_strength':'standard'}}; body=dict(body0); body['input_digest']=digest(body0)
    idem='probe:'+rid; common={'Content-Type':'application/json','X-Request-ID':rid,'Idempotency-Key':idem,'X-Tonevyra-Schema-Version':'t032.planner.request.v1'}
    unauth_status,_=call(base+'/api/v1/plans','POST',body,common)
    auth={**common,'Authorization':'Bearer '+key}; s1,r1=call(base+'/api/v1/plans','POST',body,auth); s2,r2=call(base+'/api/v1/plans','POST',body,auth)
    body2=json.loads(json.dumps(body)); body2['preferences']['correction_strength']='aggressive'; no={k:v for k,v in body2.items() if k!='input_digest'}; body2['input_digest']=digest(no); s3,r3=call(base+'/api/v1/plans','POST',body2,auth)
    valid=s1==200 and r1.get('request_id')==rid and r1.get('input_digest')==body['input_digest'] and r1.get('plan_digest')==digest(r1.get('plan'))
    replay=s2==200 and r2.get('replayed') is True and r2.get('plan_digest')==r1.get('plan_digest')
    conflict=s3==409
    ev={'schema_version':'t032.live_server_evidence.v1','ticket':'T032','base_url':base,'https_verified':True,'liveness':live,'readiness':ready,'version_endpoint':version_status==200,'version':version,'unauthorized_rejected':unauth_status in (401,403),'authorized_plan_valid':valid,'idempotent_replay':replay,'idempotency_conflict_rejected':conflict,'secret_redaction_verified':False,'implementation_build':a.implementation_build,'note':'secret_redaction_verified must be set from independent server-log inspection before strict verification'}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(ev,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(ev,ensure_ascii=False,indent=2)); return 0 if all([live,ready,version_status==200,unauth_status in (401,403),valid,replay,conflict]) else 1
if __name__=='__main__': raise SystemExit(main())
