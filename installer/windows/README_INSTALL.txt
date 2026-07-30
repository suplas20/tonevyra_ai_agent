Tonevyra AI - Windows 설치 안내
================================

이 설치 프로그램은 사용자 단위(per-user) 올인원 설치입니다. EXE 실행 후
관리자 승인(UAC)과 설치 버튼 1회 외에 별도의 설정 단계는 없습니다.

설치 위치
---------
- 애플리케이션 : %LOCALAPPDATA%\Programs\TonevyraAI
- 사용자 설정   : %LOCALAPPDATA%\TonevyraAI
- 설치 영수증/로그 : %PROGRAMDATA%\TonevyraAI\install-receipts

포함 구성요소
-------------
1. 메인 앱 실행 파일 (TonevyraAI.exe)과 실행에 필요한 런타임/DLL/site-packages
2. 앱 리소스(resources), 기본 설정 템플릿(.env.example), 트레이 아이콘
3. 로컬 AI 모델 (models\qwen3-vl-4b-instruct, 가중치/설정/토크나이저)
4. Lightroom 연동 플러그인 (TonevyraAI.lrplugin)
5. 설치/제거 구성 (Inno Setup 기본 제거 관리자 등록)
6. PostgreSQL 다운로드/설치 및 tonevyra_agent DB, tonevyra_app 역할 초기화
7. 설치 진행 로그, 실패 원인 표시, PowerShell 진행 창

설치 흐름
---------
파일 배치 (Inno Setup 네이티브)
  -> 로컬 데이터베이스   : PostgreSQL 다운로드/무결성·서명 검증/무인 설치
  -> 데이터베이스 초기화 : 역할/DB 생성, 자격 증명 저장, Alembic 스키마, 검증, 스모크
  -> Lightroom 연동      : Lightroom Classic 감지 시 플러그인 연결, 없으면 PENDING
  -> 백그라운드 에이전트 : 현재 사용자 자동 시작 등록
  -> 최종 검사           : doctor 게이트 통과 후에만 실행/성공 처리

PostgreSQL
----------
PostgreSQL 설치 파일은 이 패키지에 포함되지 않습니다. 설치 중 승인된 공식
호스트에서 안정 GA 버전을 내려받아 SHA-256과 Authenticode 서명을 검증한 뒤
무인 설치합니다. 기존 PostgreSQL 클러스터/데이터는 보존됩니다.

Lightroom Classic
-----------------
Lightroom Classic은 사용자가 직접 관리합니다. 설치되어 있지 않아도 Tonevyra
기본 설치는 완료될 수 있으며 이때 Lightroom 연동은 PENDING으로 표시됩니다.

제거
----
제거는 애플리케이션 파일만 제거하고 데이터베이스, 사진, 내보내기 결과,
설정은 기본적으로 보존합니다. 데이터베이스를 완전히 삭제하려면 설치 폴더의
Remove-TonevyraDatabase.ps1 을 명시적으로 실행하십시오.

주의
----
릴리스 배포본은 Authenticode 코드 서명과 제3자 라이선스 고지가 필요합니다.
현재 개발 빌드는 코드 서명이 적용되어 있지 않을 수 있습니다.
