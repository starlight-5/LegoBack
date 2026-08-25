legoback
========

[![CI](https://github.com/starlight-5/LegoBack/actions/workflows/ci.yml/badge.svg)](https://github.com/starlight-5/LegoBack/actions/workflows/ci.yml)
![Python versions](https://img.shields.io/badge/python-3.11%2B-blue.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

[English](README.md) | 한국어

legoback은 AI 기반 백엔드 초기 환경 설정 도구입니다. 자연어로 만들고 싶은 서비스를
설명하면 AI가 필요한 모듈을 추천하고, 검수된 코드만 조립해 바로 실행 가능한
FastAPI 프로젝트를 생성합니다.

원칙: **AI는 추천만, 코드는 배달만.** LLM은 실제로 프로젝트에 들어가는 코드를
작성하지 않으며, 같은 선택이면 항상 같은 결과(결정적 출력)를 냅니다.


Requirements
------------

### Python & Build Tools

- **Python**: 3.11 이상 (팀 표준은 3.12, CI와 동일)
- **pip**: 편집 가능 설치(`-e`) 지원 필요 — `templates/`가 저장소 루트에 있어
  일반 설치로는 템플릿을 찾지 못함

### Runtime Dependencies

주요 의존성 (전체/고정 버전은 [pyproject.toml](pyproject.toml) 참고):

| 패키지 | 용도 |
|---|---|
| typer | CLI 명령어 파서 (`legoback new ...`) |
| questionary | 화살표 키 + 스페이스 체크박스 UI |
| pydantic | manifest 스키마 / AI 분석 결과 계약 |
| jinja2 | 렌더링형 파일 생성 (main.py, docker-compose 등) |
| pyyaml | 각 모듈의 manifest.yaml 파싱 |
| packaging | 버전 범위(SpecifierSet) 교집합 검사 |
| google-genai | Gemini 호출 (AI 모듈 추천) |
| python-dotenv | .env에서 GEMINI_API_KEY 등 자동 로드 |

### Optional

- **`GEMINI_API_KEY`** — 없으면 AI 추천 대신 전체 모듈 목록 수동 선택으로 대체됨


Getting Started
----------------

### 빠른 시작 (팀원용)

#### 1. 가상환경 생성 및 설치

```bash
python -m venv .venv           # 가상환경 생성
.venv\Scripts\activate         # 가상환경 활성화
pip install -e ".[dev]"        # 개발 의존성 설치
```

#### 2. 환경변수 설정

```bash
copy .env.example .env
# GEMINI_API_KEY 채우기 (AI 추천용, 없으면 전체 목록 수동 선택으로 대체)
```

#### 3. 테스트 확인

```bash
pytest -s                      # 49개 테스트 통과 확인
```

#### 4. 프로젝트 생성

```bash
legoback new my-blog           # 대화형 생성 흐름 실행
```

### 데모

```bash
legoback new demo-blog
# "블로그 만들거야. 로그인 필요해" 입력
# → Gemini API가 분석해 settings, jwt-auth, database 추천 (API 키 없으면 전체 목록 수동 선택으로 대체)
# → 체크박스 선택 → 생성 (생성 직후 venv·기본 의존성 설치까지 자동 실행됨)
cd demo-blog
pip install -e ".[dev]"    # 테스트용 dev 도구(pytest 등)만 추가 설치
pytest                     # 테스트 통과
uvicorn src.main:app --reload                        # /docs 에서 /health 확인
```


Architecture
------------

legoback은 자연어 설명을 입력받아 AI가 모듈을 추천하고, 충돌 검사를 통과한
모듈만 조립해 실행 가능한 프로젝트를 생성합니다.

```
입력(자연어) → [B] AI 분석·추천 → [D] 선택 UI
  → [A] 해석·충돌 검사 → [A] 조립·생성
```

- **AI 추천은 참고용입니다.** 실제 조립은 항상 `modules/` 아래 검수된 manifest와
  파일만 사용하며, 환각(존재하지 않는 모듈 추천)은 검증 단계에서 제거됩니다.
- **충돌 검사는 조립 전에 이루어집니다** — 선택된 모듈 간 버전/라우트/환경변수
  충돌을 검사해, 실패 시 원인·관련 모듈·해결 제안까지 출력하고 생성 흐름을
  중단합니다.

예시 해결 제안:
- 라우트 prefix 변경
- 환경변수 이름 변경
- 서로 충돌하는 의존성 조합 피하기


Contents in This Repository
----------------------------

### 저장소 구조 = 파트 소유권

```
src/scaffold/
├── engine/     # 조합 엔진 (구분 2·3)
├── ai/         # LLM 분석·추천 (구분 1)
├── ui.py       # 인터랙티브 화면 (4.2~4.4)
└── cli.py      # 명령어·전체 흐름 (4.1, 2.1)
templates/      # 생성 프로젝트용 Jinja2 템플릿 (렌더링형 파일)
modules/        # 검수 모듈 (모듈당 manifest.yaml + files/)
tests/          # 엔진 커버리지 70% 이상 유지 (CI 게이트)
docs/           # 모듈 기여 가이드 (구분 5)
```

* `pyproject.toml` — 패키지 정의 및 의존성
* `.env.example` — 필요한 환경변수 템플릿 (GEMINI_API_KEY 등)
* `.github/workflows/ci.yml` — 이 저장소 자체의 CI (생성 프로젝트로 배달되는
  `modules/ci`와는 별개)
* `docs/CONTRIBUTING-MODULES.md` — 새 모듈 추가 가이드
* `LICENSE` — Apache-2.0 전문

### 노션 명세 ↔ 코드 매핑

각 파일 상단과 함수 docstring에 `[번호]`로 담당 스펙이 표시되어 있습니다.
노션에서 자기 항목 번호를 확인하고 아래에서 파일을 찾으면 됩니다.

| 노션 구분 | 상세 기능 | 파일 | 상태 |
|---|---|---|---|
| 1.1 입력 처리 | 1.1.1~1.1.5 | `cli.py` (_normalize, new) | 뼈대 완료, 메시지 다듬기 TODO |
| 1.2 AI 분석 | 1.2.1 LLM 연동 | `ai/recommender.py` `_call_llm` | 완료 (Gemini API 연동, 구조화 출력) |
| 1.2 AI 분석 | 1.2.2 계약 | `ai/schema.py` AnalysisResult | 완료 (변경은 B·D 합의) |
| 1.2 AI 분석 | 1.2.3 검증 | `ai/recommender.py` analyze | 완료 (환각 모듈 제거 + 필수 모듈 보강) |
| 1.3 추천 | 1.3.1~1.3.4 | `engine/loader.py`, `recommender.py`, `cli.py` | 완료 |
| 2.1 선택·확인 | 2.1.1~2.1.3 | `cli.py` run_init_flow 루프 | 완료 |
| 2.2 해석 | 2.2.1 파싱 | `engine/manifest.py`, `loader.py` | 완료 |
| 2.2 해석 | 2.2.2 그래프 | `engine/resolver.py` resolve | 완료 (테스트 포함) |
| 2.2 해석 | 2.2.3 추출 | `engine/resolver.py` collect_env | 완료 |
| 2.3 뼈대 | 2.3.1 | `engine/generator.py` create_skeleton | 완료 (완료 기준 테스트 포함) |
| 2.4 병합 | 2.4.1~2.4.4 | `engine/generator.py` | 완료 |
| 2.5 Docker | 2.5.1~2.5.4 | `generator.py` write_docker + 템플릿 | 완료 (top-level `volumes:` 선언 버그 수정 반영) |
| 3.1 버전 충돌 | 3.1.1~3.1.4 | `engine/conflicts.py` check_versions | 판정 완료, 3.1.3 최적 버전 TODO |
| 3.2 기능 충돌 | 3.2.1~3.2.2 | `conflicts.py` check_routes/env | 완료 / 3.2.3 스키마 TODO |
| 3.3 해결 제시 | 3.3.1~3.3.4 | `conflicts.py` check_routes 등 | 라우트 충돌 해결 제안 완료, 버전·환경변수 제안 문구 생성은 TODO |
| 4.1 명령어 | 4.1.1~4.1.4 | `cli.py` | 완료 |
| 4.2 선택 UI | 4.2.1~4.2.4 | `ui.py` select_modules | 완료 (questionary) |
| 4.3 진행 표시 | 4.3.1~4.3.3 | `ui.py` step (스피너) | 완료 |
| 4.4 메시지 | 4.4.1~4.4.4 | `ui.py`, `engine/errors.py` | 완료 |
| 5.x 생태계 | 5.1~5.2 | `docs/CONTRIBUTING-MODULES.md` | 초안 |


Modules
-------

모듈 제작자는 모듈을 추가하기 전에 충돌 검사를 통과해야 합니다.

- **버전 충돌** — 요구 조건의 교집합이 있으면 통과, 없으면 실패; 공통 범위가
  있으면 권장 버전도 함께 제시
- **라우트 충돌** — prefix 또는 엔드포인트 경로가 중복되면 실패
- **환경변수 충돌** — 같은 변수명에 서로 다른 기본값을 쓰면 실패

### 등록된 모듈 (10종)

**[settings](modules/settings)** — ✅ 완료 (실코드 + 테스트)

**[docker](modules/docker)** — ✅ 완료 (docker-compose.yml named volume 선언 버그 수정)

**[ci](modules/ci)** — ✅ 설정 파일형 — 사실상 완료 (DB 서비스 블록 자동 추가만 회의 대기)

**[cors](modules/cors)**, **[logging](modules/logging)**, **[exception-handler](modules/exception-handler)** — ✅ 완료 (registrations 필드로 main.py 자동 연결, 테스트 포함)

**[database](modules/database)** — ✅ 완료 (PostgreSQL/MySQL/Supabase + Alembic, db_type별 조건부 파일·env·docker_services)

**[redis-cache](modules/redis-cache)** — ✅ 완료 (접속 코드 + `@cached` 데코레이터, 테스트 포함)

**[jwt-auth](modules/jwt-auth)** — ✅ 완료 (bcrypt 해싱 + JWT access/refresh 토큰)

**[rbac](modules/rbac)** — ✅ 완료 (jwt-auth `decode_access_token` 연동, 역할 기반 접근 제어)

새 모듈 추가 = `modules/<이름>/` 폴더 + manifest.yaml + files/. 코드 수정 불필요.
자세한 방법: [docs/CONTRIBUTING-MODULES.md](docs/CONTRIBUTING-MODULES.md)


Development
-----------

### 테스트 실행

```bash
pytest -s              # 전체 테스트 (-s 플래그로 출력 포함)
pytest --cov=src/scaffold/engine --cov-fail-under=70   # CI와 동일한 커버리지 게이트
```

### CI

푸시/PR마다 GitHub Actions가 Python 3.12 기준으로 `pip install -e ".[dev]"` 후
엔진 커버리지 70% 게이트를 검사합니다.
자세한 내용: [.github/workflows/ci.yml](.github/workflows/ci.yml)

### 새 모듈 기여하기

1. `modules/<모듈이름>/manifest.yaml` 작성 (버전 범위·라우트·환경변수 명시)
2. `modules/<모듈이름>/files/`에 실제 코드 배치
3. 충돌 검사 통과 확인 (`pytest`)
4. 자세한 절차는 [docs/CONTRIBUTING-MODULES.md](docs/CONTRIBUTING-MODULES.md) 참고


License
-------

Apache-2.0. 전문은 [LICENSE](LICENSE) 파일을 참고하세요.
