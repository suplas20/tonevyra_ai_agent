F:\tonevyra_ai_agent 에서 T-020 Lightroom Final Export Adapter를 구현하라.

먼저 다음 문서를 최우선 기준으로 읽어라.

F:\tonevyra_ai_agent\.docs\t020\T-020_Lightroom_Final_Export_Adapter_Work_Order.md

관련 필수 파일:
- F:\tonevyra_ai_agent\AGENTS.md
- F:\tonevyra_ai_agent\CLAUDE.md
- F:\tonevyra_ai_agent\skills\lightroom-final-export-adapter\SKILL.md
- F:\tonevyra_ai_agent\harness\CONTRACT_LIGHTROOM_EXPORT_ADAPTER.md

핵심 목표:
T-019 apply result가 실제 applied인 사진만 export request로 만들고, Lightroom Plugin이 해당 보정본을 사용자 조작 없이 JPEG로 내보낸 뒤 export result JSON을 기록하게 하라.

경로:
- Request: F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_requests
- Result: F:\tonevyra_ai_agent\runtime\bridge\lightroom_export_results
- Output: F:\tonevyra_ai_agent\runtime\output\temp
- Plugin: F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin

필수 기준:
- source_path와 export_path는 절대 경로
- 기본 export: JPEG, quality 95, sRGB, resize false
- 원본 덮어쓰기 금지
- manual-only export 금지
- status=exported만으로 성공 처리 금지
- 실제 export_path 파일 존재와 size>0을 확인한 후 EXPORT_DONE
- 모든 claimed request는 exported 또는 failed result를 남길 것
- timeout/retry/recovery는 bounded일 것
- 기존 T-019 apply adapter, fake worker, 기존 pipeline, 기존 문서/스킬/하네스를 삭제하거나 약화하지 말 것
- Vision, Correction Planner, Quality Gate 알고리즘은 수정하지 말 것

기존 AGENTS.md의 status/error code를 우선 사용하고 새 status나 error code를 임의로 추가하지 말라.

완료 후 실행:

python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin --strict

실제 Lightroom 테스트 후:

python .\harness\scripts\verify_lightroom_export_adapter.py --project-root F:\tonevyra_ai_agent --plugin-dir F:\tonevyra_ai_agent\lightroom\TonevyraAI.lrplugin --result-json <실제-result-json> --require-output-file --strict

기존 T-019 및 전체 하네스도 회귀 실행하고 변경 파일, 실제 output 경로, result JSON, 파일 검증, 테스트 결과, 남은 이슈를 한국어로 보고하라.
