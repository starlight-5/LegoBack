legoback
========

[![CI](https://github.com/starlight-5/LegoBack/actions/workflows/ci.yml/badge.svg)](https://github.com/starlight-5/LegoBack/actions/workflows/ci.yml)
![Python versions](https://img.shields.io/badge/python-3.11%2B-blue.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

English | [한국어](README.ko.md)

legoback is an AI-assisted backend scaffolding tool. It turns a natural-language
description of what you want to build into a recommended set of reviewed,
production-ready modules, then assembles them into a runnable FastAPI project.

Principle: **AI only recommends, code is always delivered as-is.** The same
selection always produces the same output (deterministic assembly) — the LLM
never writes the code that ends up in your project.


Requirements
------------

### Python & Build Tools

- **Python**: 3.11+ (team standard is 3.12, same as CI)
- **pip**: with editable-install (`-e`) support — required because `templates/`
  lives at the repo root and a regular install can't find it

### Runtime Dependencies

Key dependencies (see [pyproject.toml](pyproject.toml) for the full/pinned list):

| Package | Purpose |
|---|---|
| typer | CLI command parser (`legoback new ...`) |
| questionary | Arrow-key + checkbox interactive UI |
| pydantic | manifest schema / AI analysis result contract |
| jinja2 | Renders templated files (main.py, docker-compose, etc.) |
| pyyaml | Parses each module's `manifest.yaml` |
| packaging | Version-range intersection checks |
| google-genai | Calls Gemini for AI module recommendations |
| python-dotenv | Loads `GEMINI_API_KEY` etc. from `.env` |

### Optional

- **`GEMINI_API_KEY`** — without it, AI recommendation falls back to manual
  selection from the full module list


Getting Started
----------------

### Quick Start (for teammates)

#### 1. Clone and install

```bash
python -m venv .venv           # create virtualenv
.venv\Scripts\activate         # activate (Windows)
pip install -e ".[dev]"        # install with dev dependencies
```

#### 2. Configure environment

```bash
copy .env.example .env
# fill in GEMINI_API_KEY (optional — falls back to manual full-list selection without it)
```

#### 3. Verify the test suite

```bash
pytest -s                      # 53 tests should pass
```

#### 4. Generate a project

```bash
legoback new my-blog           # interactive generation flow
```

### Try It Out (currently working)

```bash
legoback new demo-blog
# enter: "블로그 만들거야. 로그인 필요해" (a blog with login)
# → Gemini analyzes the input and recommends settings, jwt-auth, database
#   (falls back to manual full-list selection without an API key)
# → confirm via checkbox UI → project generated (venv + all deps, including dev tools like pytest, are installed automatically right after generation)
cd demo-blog
.venv\Scripts\activate
pytest                      # 17 tests pass
uvicorn src.main:app --reload                        # check /auth API at /docs
```


Architecture
------------

legoback takes a natural-language description, has AI recommend modules, and
assembles only the modules that pass conflict checking into a runnable project:

```
input (natural language) → [B] AI analysis/recommendation → [D] selection UI
  → [A] resolution + conflict check → [A] assembly + generation
```

- **AI recommendations are advisory only.** Assembly always uses the reviewed
  manifests and files under `modules/`; hallucinated (non-existent) module
  recommendations are filtered out during validation.
- **Conflicts are checked before assembly** — version, route, and environment
  variable conflicts across selected modules. A failure prints the cause, the
  modules involved, and a suggested fix, then halts the generation flow.

Example suggested fixes:
- Change a route prefix
- Rename an environment variable
- Avoid combining mutually conflicting dependencies


Contents in This Repository
----------------------------

### Directory Structure

```
src/scaffold/
├── engine/     # assembly engine
├── ai/         # LLM analysis/recommendation
├── ui.py       # interactive screens
└── cli.py      # commands and overall flow
templates/      # Jinja2 templates for generated projects (rendered files)
modules/        # reviewed modules (each: manifest.yaml + files/)
tests/          # keeps engine coverage at 70%+ (CI gate)
docs/           # module contribution guide
```

* `pyproject.toml` — package definition and dependencies
* `.env.example` — required environment variable template (`GEMINI_API_KEY`, etc.)
* `.github/workflows/ci.yml` — this repo's own CI (separate from `modules/ci`,
  which is delivered *into* generated projects)
* `docs/CONTRIBUTING-MODULES.md` — guide for adding new modules
* `LICENSE` — full Apache-2.0 text


Modules
-------

Module authors must pass conflict checking before a module can be added:

- **Version conflicts** — pass if requirement ranges intersect, fail otherwise;
  a recommended version is suggested when a common range exists
- **Route conflicts** — fail if a prefix or endpoint path collides with another module
- **Environment variable conflicts** — fail if two modules use the same variable
  name with different default values

### Registered Modules (10)

**[settings](modules/settings)** — ✅ done (real code + tests)

**[docker](modules/docker)** — ✅ done (fixed a top-level named-volume declaration bug in docker-compose.yml)

**[ci](modules/ci)** — ✅ config-file module, effectively done (auto-adding a DB service block is pending team discussion)

**[cors](modules/cors)** — ✅ done, auto-wired into main.py via the `registrations` field (no test file yet)

**[logging](modules/logging)**, **[exception-handler](modules/exception-handler)** — ✅ done (auto-wired into main.py via the `registrations` field, tests included)

**[database](modules/database)** — ✅ done (PostgreSQL/MySQL via SQLAlchemy+Alembic, MongoDB via Motor+Beanie; conditional files/packages/env/docker_services per `db_type`; auto-runs `alembic upgrade head` on startup for the SQL variants, tests included)

**[redis-cache](modules/redis-cache)** — ✅ done (connection code + `@cached` decorator, tests included)

**[jwt-auth](modules/jwt-auth)** — ✅ done (bcrypt hashing + JWT access/refresh tokens; separate SQL and MongoDB variants, tests included)

**[rbac](modules/rbac)** — ✅ done (integrates with jwt-auth's `decode_access_token`, role-based access control; separate SQL and MongoDB variants, tests included)

Adding a new module = a `modules/<name>/` folder with `manifest.yaml` + `files/`.
No engine code changes required — see [docs/CONTRIBUTING-MODULES.md](docs/CONTRIBUTING-MODULES.md).


Development
-----------

### Running Tests

```bash
pytest -s              # full suite
pytest --cov=src/scaffold/engine --cov-fail-under=70   # same coverage gate as CI
```

### CI

Every push/PR runs on GitHub Actions against Python 3.12: installs with
`pip install -e ".[dev]"`, then enforces the 70% engine coverage gate.
See [.github/workflows/ci.yml](.github/workflows/ci.yml).

### Contributing a New Module

1. Write `modules/<name>/manifest.yaml` (declare version range, routes, env vars)
2. Add the real code under `modules/<name>/files/`
3. Confirm conflict checks pass (`pytest`)
4. Follow the full process in [docs/CONTRIBUTING-MODULES.md](docs/CONTRIBUTING-MODULES.md)


License
-------

Apache-2.0. See the [LICENSE](LICENSE) file for the full text.
