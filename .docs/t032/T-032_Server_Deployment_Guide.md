# T-032 Planner API 서버 배포 가이드

## 1. 기준 구성

```text
Internet
→ HTTPS 443 / Nginx
→ loopback HTTP / Uvicorn 127.0.0.1:8000
→ tonevyra-planner systemd service
→ Planner engine + idempotency store
```

Oracle Cloud 1 OCPU / 1GB는 코드 기반 Planner의 테스트 운영 기준이다. Qwen 모델은 이 서버에 설치하지 않는다.

## 2. Linux 사용자와 경로

```text
service user: tonevyra-planner
application: /opt/tonevyra-planner
virtualenv: /opt/tonevyra-planner/.venv
configuration: /etc/tonevyra-planner/planner.env
runtime data: /var/lib/tonevyra-planner
logs: journald and/or /var/log/tonevyra-planner
```

서비스는 root로 실행하지 않는다. 환경 파일은 서비스 사용자 외 읽기 권한을 제한한다.

## 3. 환경변수 예시

`harness/HARNESS_ENV_T032_PLANNER_API.example`의 production placeholders를 실제 secret manager 또는 보호된 환경 파일에 연결한다.

필수 항목:

```text
TONEVYRA_PLANNER_BIND_HOST=127.0.0.1
TONEVYRA_PLANNER_BIND_PORT=8000
TONEVYRA_PLANNER_WORKERS=1
TONEVYRA_PLANNER_EXECUTION_CONCURRENCY=1
TONEVYRA_PLANNER_API_KEY_HASHES=<secret reference>
TONEVYRA_PLANNER_IDEMPOTENCY_BACKEND=<durable backend>
TONEVYRA_PLANNER_REQUEST_MAX_BYTES=262144
TONEVYRA_PLANNER_LOG_PAYLOADS=false
```

## 4. systemd 요구사항

```text
- User/Group set to non-root service account
- WorkingDirectory fixed
- EnvironmentFile protected
- ExecStart uses virtualenv uvicorn/gunicorn command
- Restart=on-failure
- StartLimitIntervalSec and StartLimitBurst bounded
- PrivateTmp=true where compatible
- NoNewPrivileges=true
- read/write paths explicitly constrained where compatible
```

`Restart=always`와 무제한 restart loop를 완료 조건으로 인정하지 않는다.

## 5. Nginx 요구사항

```text
- TLS 1.2+ / valid certificate
- port 80 redirect or deny
- proxy only allowlisted endpoints
- client_max_body_size at or below API body limit
- proxy_connect/read timeout bounded
- Authorization header passed but never logged
- access log excludes request body and secret headers
- server tokens minimized
```

## 6. 방화벽

외부에는 443만 노출한다. Uvicorn 8000은 loopback에 bind한다. SSH는 운영 정책에 맞는 source range로 제한한다.

## 7. 배포 순서

```text
1. artifact checksum verification
2. virtualenv dependency install from locked requirements
3. configuration/secret installation
4. migration or idempotency-store readiness check
5. systemd daemon-reload and start
6. local /health/live
7. local /health/ready
8. Nginx config test and reload
9. external HTTPS health/version check
10. unauthorized and authorized API probe
11. duplicate/conflict probe
12. restart/replay probe
13. 3000 sequential soak
```

## 8. 롤백

Planner engine and policy versions are immutable release artifacts. Rollback switches the active release symlink or package version and restarts the service. Client compatibility must be confirmed before rollback. Existing idempotency records must not be silently discarded.

## 9. 백업과 보존

Planner 요청 전체 payload를 장기 로그로 저장하지 않는다. Idempotency retention은 중복 재시도 보호에 필요한 기간으로 제한한다. API key audit/rotation records와 policy version manifests는 별도 보존한다.

## 10. 운영 점검

```text
- service active and ready
- memory/CPU/file descriptor usage
- request/error/latency/replay/rate-limit counts
- certificate expiry
- key rotation status
- idempotency-store health
- log disk usage and rotation
- current planner/policy/schema versions
```
