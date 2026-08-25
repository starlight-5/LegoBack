# 모듈 기여 가이드 (초안)

<!-- [5.1] 이 문서가 모듈 생태계의 공식 규격서가 된다. 항목별 담당: C 파트 -->

## 모듈 구조
```
modules/<이름>/
├── manifest.yaml   # 배달 명세서 (필수)
└── files/          # 배달될 검수 코드 (manifest의 src 기준 경로)
```

## manifest.yaml 작성
필드 정의는 `src/scaffold/engine/manifest.py` 참고. 예제는 `modules/jwt-auth` 참고.

## 의존성 선언
- 파이썬 패키지 → `pip_packages` (버전 범위 명시)
- 다른 모듈 → `depends_on`
- 외부 서비스(DB 등) → `docker_services`
- 환경 변수 → `env_vars` (description 필수 — .env 주석이 된다)

## 자동 등록 (registrations) 
main.py에 코드 수정 없이 자동으로 연결하고 싶으면 `registrations`에 `app` 하나를
인자로 받는 함수 경로를 적는다. 예: `modules/cors`
```yaml
registrations:
  - src.core.cors.apply   # main.py가 자동으로 apply(app) 호출
```

## 조건부 옵션 (options / when)
사용자에게 선택지를 물어서 그 답에 따라 `files` / `pip_packages` / `env_vars` /
`routers` / `docker_services` 항목을 다르게 포함시키고 싶으면 `options` +
`when`을 쓴다. 실전 예제는 `modules/database` 참고 (db_type에 따라
postgresql/mysql파일·패키지·env·docker 서비스가 전부 갈린다).

```yaml
options:
  db_type:                              # 옵션 이름. 다른 모듈이 같은 이름을 쓰면
    question: "사용할 데이터베이스 종류를 선택하세요"   # 질문이 하나로 합쳐져서 한 번만 물어본다.
    choices: [postgresql, mysql]
    default: postgresql

files:
  - src: files/src/core/db.py
    dest: src/core/db.py
    when: { "db_type": ["postgresql", "mysql"] }   # 이 둘 중 하나면 포함

pip_packages:
  - sqlalchemy>=2.0                     # when 없는 항목 = 항상 포함
  - spec: psycopg2-binary>=2.9          # 조건부 패키지는 spec+when 형태로 작성
    when: { "db_type": ["postgresql"] }

env_vars:
  - name: DATABASE_URL
    default: mysql+pymysql://app:app@db-mysql:3306/app
    when: { "db_type": ["mysql"] }
```

- `when`이 없으면 항상 포함된다.
- 한 `when` 안에 키가 여러 개면 AND, 한 키의 리스트 값은 OR로 매칭된다.
  예: `{"db_type": ["mysql"], "auth": ["jwt"]}` → db_type=mysql **이면서** auth=jwt일 때만 포함.
- 아직 지원하지 않는 선택지(예: supabase)는 `choices`에 넣지 말고 TODO 주석으로 남긴다.

## 코딩 표준
- PEP 8, 라우터는 `APIRouter` + prefix 없이 작성(prefix는 manifest에서)
- 테스트 파일 포함 필수 — 테스트 없는 모듈은 머지되지 않는다
- 같은 엔드포인트를 두 번 등록하지 않는다. 예: `/auth/login` 같은 경로는 중복 시 충돌한다.
- 같은 환경변수 이름을 쓰되 기본값이 다르면 충돌한다.
- 패키지 버전은 가능한 한 교집합이 생기도록 작성한다.
- 여러 모듈이 같은 패키지에 서로 다른 범위를 요구하면, 공통으로 만족하는 버전이 있으면 그 버전을 권장한다.

## 제출
GitHub PR로 제출한다. PR을 열면 [PR 템플릿](../.github/PULL_REQUEST_TEMPLATE.md)의
체크리스트가 자동으로 채워지니, 해당 항목을 실제로 확인하고 체크한다.

### 검수 기준
리뷰어는 아래를 확인하고 승인/반려한다. 하나라도 어기면 반려.

- `manifest.yaml`이 스키마(`src/scaffold/engine/manifest.py`)를 따른다.
- 버전/라우트/환경변수 충돌 검사(`engine/conflicts.py`)를 통과한다 — 기존 모듈과
  겹치면 이 시점에 걸러진다.
- 테스트 파일이 포함되어 있고, 실제로 동작을 검증한다 (형식만 갖춘 빈 테스트 불가).
- `env_vars`마다 `description`이 채워져 있다 (.env 주석으로 그대로 노출되므로).
- `options`/`when`을 쓰는 경우, 지원하지 않는 선택지가 `choices`에 들어가 있지 않다.
- CI 통과한다. PR을 올리면 `.github/workflows/ci.yml`이 자동으로 실행하는데,
  똑같은 명령을 로컬에서 미리 돌려보면 푸시 전에 실패를 잡을 수 있다:
  ```bash
  pytest --cov=src/scaffold/engine --cov-fail-under=70
  ```
  새로 만든 모듈 하나만 먼저 확인하고 싶다면, 모듈의 `files/` 폴더로 들어가서
  돌린다 (모듈 테스트는 생성된 프로젝트 기준 경로로 임포트하므로 저장소 루트에서는
  바로 실행되지 않는다):
  ```bash
  cd modules/<모듈이름>/files
  pytest tests/ --cov=src
  ```

### 승인 절차
1. 기여자가 PR을 올리고 템플릿 체크리스트를 채운다.
2. 1인 이상의 리뷰 승인을 받는다.
3. CI 통과 + 승인 완료 후 PR 작성자가 머지한다 (강제 push/force-merge 금지).
4. 반려된 경우, 검수 기준 중 어떤 항목을 어겼는지 리뷰 코멘트에 남긴다.
