# 모듈 기여 가이드 (초안)

<!-- [5.1] 이 문서가 모듈 생태계의 공식 규격서가 된다. 항목별 담당: C 파트 -->

## 모듈 구조 [5.1.1]
```
modules/<이름>/
├── manifest.yaml   # 배달 명세서 (필수)
└── files/          # 배달될 검수 코드 (manifest의 src 기준 경로)
```

## manifest.yaml 작성 [5.1.2]
필드 정의는 `src/scaffold/engine/manifest.py` 참고. 예제는 `modules/jwt-auth` 참고. [5.1.5]

## 의존성 선언 [5.1.3]
- 파이썬 패키지 → `pip_packages` (버전 범위 명시)
- 다른 모듈 → `depends_on`
- 외부 서비스(DB 등) → `docker_services`
- 환경 변수 → `env_vars` (description 필수 — .env 주석이 된다)

## 코딩 표준 [5.1.4]
- PEP 8, 라우터는 `APIRouter` + prefix 없이 작성(prefix는 manifest에서)
- 테스트 파일 포함 필수 — 테스트 없는 모듈은 머지되지 않는다 [5.2.3]

## 제출 [5.2.1]
GitHub PR로 제출. TODO: PR 템플릿, 검수 기준 문서 [5.2.2], 승인 절차 [5.2.4]
