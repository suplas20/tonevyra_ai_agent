---
name: project-scope
description: Keep the MVP focused on the local photo correction agent pipeline. Use this skill when starting ANY implementation task, reviewing changes, or deciding whether a feature/dependency belongs in MVP — even small helpers. Always consult before adding anything not listed as Must Build.
---

# Project Scope Control

## MVP 파이프라인 (단일 기준)

```text
Input folder
→ 파일 감지 + 안정화            (folder-watcher)
→ PostgreSQL task 등록          (postgresql-persistence)
→ 1024px sRGB preview 생성      (vision-analysis)
→ vision 모델 분석              (model-security, vision-analysis)
→ correction planning           (correction-planning)
→ Lightroom JSON bridge/export  (lightroom-bridge)
→ quality gate                  (quality-gate)
→ PASS / REVIEW_REQUIRED / FAILED
→ 전 구간 영속화 + 아티팩트     (postgresql-persistence, artifact-storage)
```

## MVP must include

folder watcher, 파일 안정화, PostgreSQL 영속화, 로컬 아티팩트 저장,
1024px sRGB JPEG preview, MockVisionBackend, 교체 가능한 vision backend 인터페이스,
Qwen2.5-VL-3B 4bit technical stable candidate + Qwen3-VL-4B commercial/default candidate slot, correction planner,
Lightroom Classic JSON bridge + 최소 Lua plugin PoC, quality gate, CLI, crash recovery, testing harness.

## MVP must not include

```text
Full React dashboard          FastAPI-first 구현
블로그/인스타/홈페이지 자동화   장비 DB 어시스턴트 / 일반 챗봇
SaaS 계정 / 멀티유저           Redis / MinIO / NATS / Celery / Kubernetes
complex worker pool           2048px·multi-crop 입력 기본값화
Lightroom neutral preview 기본값화    상위 모델(7B/8B+) 기본값화
```

## Decision rule

확신이 없으면 end-to-end 파이프라인을 증명하는 가장 작은 구현을 선택한다.
범위 질문의 답은 이 파일이며, 다른 코드베이스에서 유추하지 않는다.

## Guardrails

- "작은 헬퍼 서비스"도 서비스다 — 요청 없으면 거부.
- Deferred 항목은 인터페이스/config 슬롯까지만 설계하고 선구현하지 않는다.
- 규칙과 충돌하는 요청은 구현하지 말고 충돌을 보고한다 (AGENTS.md §10).

## Acceptance criteria

CLI에서 동작, mock vision + fake Lightroom으로 사진 1장 end-to-end 처리,
PostgreSQL 상태 영속화, 로컬 아티팩트 저장, 대시보드 불필요, 외부 API 호출 없음.

## T-032 Scope Exception

The product remains local-first for image/model/Lightroom processing. T-032 introduces one approved remote component: the code-based Correction Planner Service. This does not authorize image upload, remote model inference, general FastAPI migration of the Agent, SaaS billing, or browser dashboard work.

## T-033 Product Packaging Scope

T-033 adds Windows/macOS product installers without changing the photo-processing state machine. Python 3.11.9 is bundled. PostgreSQL is downloaded at install time. Lightroom remains user-managed. Planner rules remain server-only under T-032.
