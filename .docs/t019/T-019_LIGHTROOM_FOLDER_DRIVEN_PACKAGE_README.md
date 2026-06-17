# Tonevyra T-019 Folder-Driven Lightroom Plugin Package

이 패키지는 Lightroom Classic 플러그인 실구현 작업을 시작하기 위한 T-019 수정 산출물이다.

중요 정정: Tonevyra AI는 사용자가 Lightroom에서 사진을 선택하고 메뉴를 눌러 보정하는 제품이 아니다. 사용자는 지정 폴더에 사진을 넣고, agent가 이를 감지/분석한 뒤 Lightroom plugin을 자동 적용 작업자로 사용한다.

## 포함 파일

```text
.docs/t019/
  T-019_Lightroom_Plugin_Implementation_Work_Order.md
  T-019_Codex_Prompt.md
  Lightroom_Plugin_Bridge_Contract.md
  Lightroom_Plugin_Live_Test_Checklist.md

skills/
  lightroom-plugin-implementation/SKILL.md
  lightroom-live-test/SKILL.md

harness/
  CONTRACT_LIGHTROOM_PLUGIN.md
  HARNESS_ENV_LIGHTROOM_PLUGIN.example
  prompts/06_lightroom_plugin_real_implementation_prompt.md
  fixtures/lightroom_plugin/*.json
  scripts/verify_lightroom_plugin_structure.py
  scripts/run_lightroom_bridge_contract_test.py
  scripts/verify_lightroom_live_test_evidence.py
  scripts/run_lightroom_worker_mapping_test.py

plugin_scaffold/
  TonevyraAI.lrplugin/
```

## 프로젝트 반영 방법

1. 현재 프로젝트 루트에 이 패키지의 `.docs/t019/`, `skills/`, `harness/` 내용을 병합한다.
2. 이전 T-019 선택 사진 기반 문서는 폐기하거나 이 패키지로 교체한다.
3. 기존 파일을 무조건 덮어쓰지 말고, 같은 파일이 있으면 diff를 확인한다.
4. `plugin_scaffold/`는 참고용이다. 실제 구현 위치는 프로젝트 canonical path에 맞춘다.
5. Codex에는 `.docs/t019/T-019_Codex_Prompt.md`를 작업 지시로 전달한다.

## 하네스 실행

```bash
python harness/scripts/verify_lightroom_plugin_structure.py --plugin-dir plugin_scaffold/TonevyraAI.lrplugin
python harness/scripts/run_lightroom_bridge_contract_test.py
python harness/scripts/run_lightroom_worker_mapping_test.py
python harness/scripts/verify_lightroom_live_test_evidence.py --evidence harness/fixtures/lightroom_plugin/valid_apply_result.json
```

실제 Lightroom Classic live test 후에는 fixture가 아니라 실제 result/evidence 파일을 넣어 검증한다.

```bash
python harness/scripts/verify_lightroom_live_test_evidence.py --evidence runtime/bridge/lightroom_apply_results/<request_id>.json
```
