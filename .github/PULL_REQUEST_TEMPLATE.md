<!-- 새 모듈 추가 PR용 템플릿. 모듈과 무관한 PR(엔진/AI/UI 등)은 이 체크리스트를 지워도 됩니다. -->

## 모듈명
<!-- 예: redis-cache -->

## 요약
<!-- 이 모듈이 무엇을 하는지 한두 줄 -->

## 체크리스트
- [ ] `modules/<이름>/manifest.yaml` + `files/` 구조를 따름
- [ ] `pip_packages` 버전 범위 명시 (다른 모듈과 교집합 확인)
- [ ] `env_vars`에 `description` 작성함
- [ ] 라우트 prefix가 기존 모듈과 겹치지 않음
- [ ] 조건부 옵션(`options`/`when`)을 쓴다면 [CONTRIBUTING-MODULES.md](../docs/CONTRIBUTING-MODULES.md) 문법을 따름
- [ ] 테스트 파일 포함 (`files/tests/`)
- [ ] `pytest` 로컬 통과 확인
- [ ] CI 통과 확인

## 관련 이슈
- [ ]
