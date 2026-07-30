#!/usr/bin/env python3
"""Verify T-033 all-in-one and database bootstrap evidence."""
from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED_OBJECTS={"image_tasks","task_artifacts","task_events","stage_results","quality_results","feedback_records","learning_samples","v_task_summary","alembic_version"}

def load(path:Path): return json.loads(path.read_text(encoding="utf-8"))

def verify_all_in_one(d):
    failures=[]
    expected={"schema_version":"t033.all_in_one.install.v1","ticket":"T033","single_install_session":True,"manual_prerequisite_steps":0,"manual_database_steps":0,"os_elevation_only":True,"postgres_unattended_install":True,"database_bootstrap_automatic":True,"startup_registration_automatic":True,"post_install_doctor_passed":True,"completed":True}
    for k,v in expected.items():
        if d.get(k)!=v: failures.append(f"all_in_one:{k} expected={v!r} actual={d.get(k)!r}")
    if d.get("platform") not in {"windows","macos"}: failures.append("all_in_one:invalid platform")
    return failures

def verify_db(d):
    failures=[]
    expected={"schema_version":"t033.database.bootstrap.v1","ticket":"T033","postgres_service_ready":True,"role_exists":True,"database_exists":True,"runtime_role_non_superuser":True,"localhost_only":True,"alembic_head_matches":True,"read_write_smoke_rolled_back":True,"credential_store_verified":True,"completed":True}
    for k,v in expected.items():
        if d.get(k)!=v: failures.append(f"database:{k} expected={v!r} actual={d.get(k)!r}")
    missing=REQUIRED_OBJECTS-set(d.get("required_objects",[]))
    if missing: failures.append("database:missing_objects="+",".join(sorted(missing)))
    return failures

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--all-in-one-evidence',type=Path,required=True); ap.add_argument('--database-evidence',type=Path,required=True); a=ap.parse_args()
    failures=verify_all_in_one(load(a.all_in_one_evidence))+verify_db(load(a.database_evidence))
    if failures:
        print('FAIL: T033 all-in-one install'); [print('- '+x) for x in failures]; return 1
    print('PASS: T033 all-in-one installer evidence')
    print('PASS: T033 automatic database bootstrap/schema evidence')
    return 0
if __name__=='__main__': raise SystemExit(main())
