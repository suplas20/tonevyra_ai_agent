# Image Fixtures

`sample_underwater_01.jpg`는 하네스용 synthetic underwater sample입니다.
실제 고객 사진을 넣지 말고, 개발/테스트용 더미 이미지만 보관하세요.

실제 품질 검증 단계에서는 별도 `private_fixtures/` 또는 로컬 전용 경로를 사용하고 Git에는 올리지 않습니다.

## T-029 background-person fixture

`t029_background_person_red_recovery.jpg` is the canonical T-029 case. The small upper-left background person is not reliably detected by Subject, People, or Object, so the expected strategy is a deterministic radial template around the faded red garment. Use it only for local/offline testing.
