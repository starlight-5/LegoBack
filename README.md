# fastapi-scaffold

AI 기반 백엔드 초기 환경 설정 도구. 자연어 설명 → 모듈 추천 → 검수된 코드 조립.

원칙: **AI는 추천만, 코드는 배달만.** 같은 선택이면 항상 같은 결과(결정적 출력).

## 빠른 시작 (팀원용)

```bash
pip install -e ".[dev]"
pytest                      # 14개 테스트 통과 확인
scaffold new my-blog        # 대화형 생성 흐름 실행
```

## 저장소 구조 = 파트 소유권

```
src/scaffold/
├── engine/     # A 파트 — 조합 엔진 (구분 2·3)
├── ai/         # B 파트 — LLM 분석·추천 (구분 1)
├── ui.py       # D 파트 — 인터랙티브 화면 (4.2~4.4)
└── cli.py      # D 파트 — 명령어·전체 흐름 (4.1, 2.1)
templates/      # A 파트 — 생성 프로젝트용 Jinja2 템플릿 (렌더링형 파일)
modules/        # C 파트 — 검수 모듈 (모듈당 manifest.yaml + files/)
tests/          # 엔진 커버리지 70% 이상 유지 (CI 게이트)
docs/           # C 파트 — 모듈 기여 가이드 (구분 5)
```

## 노션 명세 ↔ 코드 매핑

각 파일 상단과 함수 docstring에 `[번호]`로 담당 스펙이 표시되어 있다.
노션에서 자기 항목 번호를 확인하고 아래에서 파일을 찾으면 된다.

| 노션 구분 | 상세 기능 | 파일 | 상태 |
|---|---|---|---|
| 1.1 입력 처리 | 1.1.1~1.1.5 | `cli.py` (_normalize, new) | 뼈대 완료, 메시지 다듬기 TODO |
| 1.2 AI 분석 | 1.2.1 LLM 연동 | `ai/recommender.py` `_call_llm` | **TODO — 키워드 휴리스틱 대체 중** |
| 1.2 AI 분석 | 1.2.2 계약 | `ai/schema.py` AnalysisResult | 완료 (변경은 B·D 합의) |
| 1.2 AI 분석 | 1.2.3 검증 | `ai/recommender.py` analyze | 뼈대 완료 |
| 1.3 추천 | 1.3.1~1.3.4 | `engine/loader.py`, `recommender.py`, `cli.py` | 뼈대 완료 |
| 2.1 선택·확인 | 2.1.1~2.1.3 | `cli.py` run_init_flow 루프 | 완료 |
| 2.2 해석 | 2.2.1 파싱 | `engine/manifest.py`, `loader.py` | 완료 |
| 2.2 해석 | 2.2.2 그래프 | `engine/resolver.py` resolve | 완료 (테스트 포함) |
| 2.2 해석 | 2.2.3 추출 | `engine/resolver.py` collect_env | 완료 |
| 2.3 뼈대 | 2.3.1 | `engine/generator.py` create_skeleton | 완료 (완료 기준 테스트 포함) |
| 2.4 병합 | 2.4.1~2.4.4 | `engine/generator.py` | 완료 |
| 2.5 Docker | 2.5.1~2.5.4 | `generator.py` write_docker + 템플릿 | 뼈대 완료 (docker 모듈 필요) |
| 3.1 버전 충돌 | 3.1.1~3.1.4 | `engine/conflicts.py` check_versions | 판정 완료, 3.1.3 최적 버전 TODO |
| 3.2 기능 충돌 | 3.2.1~3.2.2 | `conflicts.py` check_routes/env | 완료 / 3.2.3 스키마 TODO |
| 3.3 해결 제시 | 3.3.1~3.3.4 | `conflicts.py` 하단 TODO | **미착수 — D 파트와 협의 필요** |
| 4.1 명령어 | 4.1.1~4.1.4 | `cli.py` | 완료 |
| 4.2 선택 UI | 4.2.1~4.2.4 | `ui.py` select_modules | 완료 (questionary) |
| 4.3 진행 표시 | 4.3.1~4.3.3 | `ui.py` step | 4.3.3만 완료, 바·스피너 TODO |
| 4.4 메시지 | 4.4.1~4.4.4 | `ui.py`, `engine/errors.py` | 완료 |
| 5.x 생태계 | 5.1~5.2 | `docs/CONTRIBUTING-MODULES.md` | 초안 |

## 모듈 현황 (10종 전체 등록)

| 모듈 | 상태 |
|---|---|
| settings | ✅ 완료 (실코드 + 테스트) |
| docker, ci | ✅ 설정 파일형 — 사실상 완료 (CI의 DB 서비스 블록만 회의 대기) |
| cors, logging, exception-handler | 🔶 코드 동작 — main.py 자동 연결(registrations 필드)만 회의 대기 |
| database, redis-cache | 🔶 접속 코드 동작 — Alembic 셋업, 캐시 데코레이터 TODO |
| jwt-auth | 🔶 API 스텁 — 해싱·토큰 로직 TODO |
| rbac | 🔶 스텁 — jwt-auth 토큰 해석 연동 TODO |

새 모듈 추가 = `modules/<이름>/` 폴더 + manifest.yaml + files/. 코드 수정 불필요.
자세한 방법: `docs/CONTRIBUTING-MODULES.md`

## 데모 (현재 동작하는 것)

```bash
scaffold new demo-blog
# "블로그 만들거야. 로그인 필요해" 입력
# → settings, jwt-auth, database 추천 (현재는 키워드 휴리스틱)
# → 체크박스 선택 → 생성
cd demo-blog && pip install -e ".[dev]" && pytest   # 3개 테스트 통과
uvicorn src.main:app --reload                        # /docs 에서 /auth API 확인
```
