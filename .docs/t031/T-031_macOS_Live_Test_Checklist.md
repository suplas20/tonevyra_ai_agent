# T-031 macOS Live Test Checklist

## 환경 기록

```text
macOS version/build:
Mac model/chip:
Unified memory:
Tonevyra build SHA-256:
Lightroom Classic version:
Model revision/quantization:
Backend:
```

## 테스트

- [ ] `arm64` 네이티브 실행이며 Rosetta가 필요하지 않다.
- [ ] 메뉴 막대 아이콘이 라이트/다크 모드에서 식별된다.
- [ ] 메뉴의 pause/resume/rescan/dashboard/quit가 동작한다.
- [ ] 두 번째 실행은 기존 인스턴스를 활성화하고 종료한다.
- [ ] 로그인 항목 등록/해제가 동작한다.
- [ ] 선택한 입력 폴더 권한을 보유한다.
- [ ] 큰 파일 복사 중에는 작업을 시작하지 않는다.
- [ ] 복사 완료 후 한 번만 큐에 등록한다.
- [ ] MPS에서 실제 사진 1장 분석이 성공한다.
- [ ] CPU fallback 발생 여부가 evidence에 명시된다.
- [ ] Lightroom macOS 플러그인이 Agent와 연결된다.
- [ ] 사진 1장 end-to-end 보정이 완료된다.
- [ ] 10장 순차 처리 후 메모리가 단조 증가하지 않는다.
- [ ] idle timeout 후 Inference Worker가 종료된다.
- [ ] 재시작 후 미완료 큐가 복구된다.

## 필수 첨부

```text
macos_live_evidence.json
menu_bar_idle.png
menu_bar_processing.png
process_architecture.txt
mps_probe.log
memory_soak.csv
lightroom_result.json
```
