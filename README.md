# API Sentinel 🛡️

**AI-powered API testing and debugging agent.**

API Sentinel takes an OpenAPI/Swagger specification and autonomously tests every endpoint — making real HTTP calls, diagnosing failures, and generating a professional debug report. No more clicking through Swagger UI one endpoint at a time.

---

## The problem it solves

Testing a REST API manually is tedious:
- Swagger UI is one call at a time
- Postman collections need manual setup per endpoint
- New APIs take hours to explore and document
- Comparing staging vs production means running the same tests twice

API Sentinel reads the spec, authenticates if needed, decides what to test, makes the calls, interprets the results, and hands you a report — like a QA engineer that works in seconds.

---

## How it works

```
OpenAPI Spec ──► fetch_spec ──► [LLM Agent] ──► http_request × N ──► save_report + finish_run
                                                                              ↓
                                                                    report.md + report.html
```

The agent (LLM via [litellm](https://github.com/BerriAI/litellm)) drives four tools:

| Tool | What it does |
|------|-------------|
| `fetch_spec` | Downloads and parses the OpenAPI spec, extracts all endpoints |
| `http_request` | Makes real HTTP calls — captures status, headers, body, latency |
| `save_report` | Saves a Markdown + HTML report to `reports/` |
| `finish_run` | Records final counts for CI/CD exit code evaluation |

The LLM decides *what* to test, *how* to construct requests from the schema, and *how to interpret* every response. Python just executes the tools.

**This is the core pattern of AI agents: Tool = eyes and hands. LLM = brain.**

---

## Features

- **Autonomous testing** — reads the spec and decides what to test, no manual setup
- **Authentication** — finds the auth endpoint, logs in, and uses the Bearer token for all subsequent calls
- **Safe mode** — blocks POST/PUT/PATCH/DELETE at the code level before they execute (not just a prompt instruction)
- **Environment comparison** — tests the same spec against two base URLs and diffs the results (staging vs prod)
- **Dual reports** — always generates both `.md` and `.html`; the HTML report has dark mode and colored status badges
- **CI/CD mode** — exits with code `1` if critical issues are found, `0` otherwise; drop it into any pipeline
- **Provider-agnostic** — powered by litellm; swap models via `LLM_MODEL` env var without touching the code

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/daniele-angeli-dev/api-sentinel
cd api-sentinel

# 2. Create virtual environment
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1
# Mac/Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
# Add ANTHROPIC_API_KEY (or any provider key supported by litellm)
```

---

## Usage

```bash
# Basic: test a public API
python api_sentinel.py --spec https://petstore.swagger.io/v2/swagger.json

# With authentication (agent finds the login endpoint automatically)
python api_sentinel.py --spec ./swagger.json --credentials admin:secret

# Safe mode — blocks all write operations before they execute
python api_sentinel.py --spec ./swagger.json --safe-mode --no-auth

# Compare staging vs production
python api_sentinel.py --spec ./swagger.json \
  --base-url https://staging.myapp.com \
  --compare-url https://api.myapp.com

# CI/CD pipeline (exits 1 if critical issues found)
python api_sentinel.py --spec ./swagger.json --no-auth --safe-mode --ci

# With API key auth + verbose output
python api_sentinel.py --spec ./swagger.json --api-key your-token --verbose
```

### All options

```
--spec URL_OR_PATH     OpenAPI spec URL or local JSON file (required)
--base-url URL         Override the base URL from the spec
--compare-url URL      Second base URL for staging vs prod comparison
--safe-mode            Block POST/PUT/PATCH/DELETE before they execute
--ci                   CI/CD mode: exit 1 on critical issues, exit 0 otherwise
--verbose              Show full tool responses during the run
--credentials USER:PASS  Username and password for authenticated APIs
--api-key KEY          API key to use as Bearer token
--no-auth              Skip the authentication prompt
```

---

## Example output

```
🛡️  API Sentinel starting...
📋 Spec:    https://petstore.swagger.io/v2/swagger.json
🤖 Model:   anthropic/claude-sonnet-4-6
🔓 Auth:    none
🔒 Safe mode: ON

📥 Fetching spec: https://petstore.swagger.io/v2/swagger.json
   ↳ ✅ Swagger Petstore — 20 endpoints found

🔍 GET     https://petstore.swagger.io/v2/pet/findByStatus?status=available
   ↳ ✅ 200 (585ms)
🔍 GET     https://petstore.swagger.io/v2/pet/1
   ↳ ⚠️ 404 (434ms)
🔍 GET     https://petstore.swagger.io/v2/user/login?username=test&password=test
   ↳ ✅ 200 (436ms)
🔒 POST    https://petstore.swagger.io/v2/pet
   ↳ 🔒 Blocked (POST) — safe mode active

💾 Saving report: petstore-report
   ↳ ✅ reports/petstore-report.md + reports/petstore-report.html (10,044 bytes)
🏁 Run complete: 6 passed / 2 failed / 12 skipped / 0 critical

✅ Done.
```

The HTML report opens in any browser — dark mode, colored status badges, no dependencies.

---

## What it actually finds

Running against the public Petstore API, API Sentinel autonomously identified:

- `GET /pet/findByStatus?status=invalid` returns `200 []` instead of `400` — missing enum validation
- `GET /store/order/1` returns `"status": "oredered"` — a typo not present in the spec enum
- `GET /store/inventory` contains garbage keys (`"string"`, `"Available "`, `"awaiable"`) — write-path lacks validation
- `GET /pet/findByTags` is deprecated but sends no `Deprecation` or `Sunset` headers

Zero hardcoded logic. The agent reasoned about each response against the spec.

---

## Project structure

```
api_sentinel/
├── api_sentinel.py   # CLI entry point (argparse)
├── agent.py          # Agent loop — drives the LLM, handles tool calls
├── tools.py          # Tool definitions (schemas) + implementations
├── reports/          # Generated reports (git-ignored)
├── .env.example      # API key template
└── README.md
```

---

## Switching models

API Sentinel uses [litellm](https://github.com/BerriAI/litellm) — swap providers without changing any code:

```bash
# Use GPT-4o instead
LLM_MODEL=openai/gpt-4o python api_sentinel.py --spec ./swagger.json

# Use Gemini
LLM_MODEL=gemini/gemini-1.5-pro python api_sentinel.py --spec ./swagger.json
```

---

## Key concepts demonstrated

- **AI agent architecture** — LLM as reasoning engine, tools as executors
- **OpenAPI/Swagger** — industry-standard API specification format
- **Agentic tool loop** — multi-step reasoning with dynamic tool selection
- **Safety by design** — safe mode enforced at code level, not prompt level
- **CLI tooling** — `argparse` with argument groups for clean UX
- **Provider abstraction** — litellm for model-agnostic integration
- **CI/CD integration** — structured exit codes for pipeline automation
- **Modular Python** — clean separation across agent, tools, and entrypoint

---

## Tech stack

- Python 3.10+
- [litellm](https://github.com/BerriAI/litellm) — provider-agnostic LLM client
- [Requests](https://requests.readthedocs.io/) — HTTP client
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment config
- OpenAPI 2.0 / 3.0 spec support (JSON)

---

## Roadmap

- [ ] YAML spec support
- [ ] Schema validation: check if response body matches the spec definition
- [ ] Custom headers: `--header "X-Tenant: mycompany"`
- [ ] HTML report with collapsible sections
