# TestPilot AI

TestPilot AI is a web-testing product prototype. Phase 5 adds bounded Playwright execution for selected Phase 4 test cases. The backend asks the OpenAI planner for one typed browser action at a time, runs it through a fixed browser-tool layer, observes the page, and evaluates the expected result. Test plans are not executed automatically.

## Architecture

```text
React dashboard -> FastAPI -> session/plan/execution repositories
						 -> Playwright inspection
						 -> Testing Agent -> OpenAI API
						 -> Execution Service -> action planner/evaluator
						 -> fixed Browser Tools -> Playwright
```

Session metadata, inspections, test plans, and execution results are held in memory. Screenshots are written to `backend/screenshots/` and served through session-scoped endpoints. Browser, context, and page resources are closed after each run. Repositories are replaceable with persistent storage later.

## Requirements

- Python 3.12+
- Node.js and npm

## Backend installation

From the repository root:

```powershell
cd backend
python -m venv .venv
\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `backend/.env` before requesting plan generation. `OPENAI_MODEL` defaults to `gpt-5.6-mini`. The key is read only by the backend and is never sent to the React app. The example file intentionally contains no key.

If PowerShell script execution is restricted, activation is optional; use `\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` instead.

Start the API from the `backend` directory:

```powershell
uvicorn app.main:app --reload
```

The API listens on `http://localhost:8000`. Interactive documentation is at `/docs`; ReDoc is at `/redoc`.

Browser configuration is read from the environment:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BROWSER_HEADLESS` | `true` | Launch Chromium without a visible window |
| `BROWSER_TIMEOUT` | `30000` | Navigation and page-operation timeout in milliseconds |
| `MAX_PAGE_TEXT_LENGTH` | `20000` | Maximum returned visible-text length |
| `MAX_CONSOLE_MESSAGES` | `100` | Maximum stored console and network messages |
| `ALLOW_LOCAL_URLS` | `false` | Allow local/private addresses for isolated development only |
| `OPENAI_API_KEY` | unset | Backend-only OpenAI API credential |
| `OPENAI_MODEL` | `gpt-5.6-mini` | OpenAI model used for structured plan generation |
| `OPENAI_TIMEOUT_SECONDS` | `60` | OpenAI request timeout |
| `MAX_AI_PAGE_TEXT` | `12000` | Maximum visible website text sent to the AI |
| `MAX_AI_LINKS` | `100` | Maximum links sent to the AI |
| `MAX_AI_ELEMENTS` | `200` | Maximum inspected elements, including select options |
| `MAX_AI_TEST_CASES` | `30` | Maximum accepted test cases per plan |
| `ACTION_TIMEOUT` | `10000` | Per browser action timeout in milliseconds |
| `NAVIGATION_TIMEOUT` | `30000` | Browser navigation timeout in milliseconds |
| `TEST_EXECUTION_TIMEOUT` | `180` | Overall per-test execution deadline in seconds |
| `MAX_ACTIONS_PER_TEST` | `30` | Maximum planner/browser action turns per test |
| `MAX_TEST_CASES_PER_EXECUTION` | `10` | Maximum cases in a batch execution request |
| `TEST_CREDENTIAL_USERNAME` | unset | Optional mock/test username, backend only |
| `TEST_CREDENTIAL_PASSWORD` | unset | Optional mock/test password, backend only |

Public HTTP/HTTPS URLs are accepted. Localhost, loopback, and non-public DNS results are blocked by default, including redirected and subresource requests. URL checks and browser interception are defense-in-depth; deploy with OS/container network egress isolation before production use. Do not enable local URLs for untrusted users.

## Frontend installation

In a second terminal, from the repository root:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

The frontend uses `http://localhost:8000/api` by default. To override it, set `VITE_API_BASE_URL` before starting Vite.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| POST | `/api/test-sessions` | Create a pending session |
| GET | `/api/test-sessions` | List sessions, newest first |
| GET | `/api/test-sessions/{id}` | Get a session |
| POST | `/api/test-sessions/{id}/inspect` | Inspect the session website in Chromium and return the latest result |
| GET | `/api/test-sessions/{id}/inspection` | Get the latest inspection result |
| GET | `/api/test-sessions/{id}/inspection/screenshot` | Serve the session screenshot as PNG |
| POST | `/api/test-sessions/{id}/generate-tests` | Generate and store a structured plan; requires a successful inspection |
| GET | `/api/test-sessions/{id}/test-plan` | Get the latest generated test plan |
| POST | `/api/test-sessions/{id}/execute` | Execute selected cases, or all cases when no IDs are supplied |
| POST | `/api/test-sessions/{id}/test-cases/{test_case_id}/execute` | Execute one planned case |
| GET | `/api/test-sessions/{id}/executions` | List execution records for the session, including running timelines |
| GET | `/api/test-sessions/{id}/executions/{execution_id}` | Get one execution record |
| GET | `/api/test-sessions/{id}/executions/{execution_id}/screenshot` | Serve execution screenshot evidence |
| DELETE | `/api/test-sessions/{id}` | Delete a session |

The AI can return only the Pydantic `BrowserAction` schema: `navigate`, `click`, `fill`, `select`, `check`, `uncheck`, `press`, `scroll`, `wait`, `read_page`, or `take_screenshot`. It cannot submit code or selectors. Targets resolve through accessible names, labels, placeholders, names, IDs, and exact visible text; ambiguous targets block instead of guessing. Request interception reuses URL/DNS SSRF protections and prevents off-site top-level navigation. Production still requires OS/container egress isolation.

An execution is marked `PASSED` only when the evaluator supplies exact evidence found in the observed page state. Missing or untraceable evidence cannot produce a pass. Action failures and safety violations are `BLOCKED`; expected behavior mismatches are `FAILED`. Action values are not stored in execution logs. Password fields use the backend-only mock credential provider, and credentials are not included in prompts, logs, or plans. Potentially destructive targets are blocked unless the user enables the explicit confirmation option in the UI.

Session modes are `EXPLORE`, `TEST`, and `FULL_TEST`. New sessions have `PENDING` status; inspection advances through `RUNNING` to `COMPLETED` or `FAILED`. Users explicitly select one or more cases before execution. Session, inspection, plan, and execution data is lost when the backend process stops.

## Tests and build

Run the backend tests from the `backend` directory after installing Chromium:

```powershell
pytest
```

Build the frontend from the `frontend` directory:

```powershell
npm.cmd run build
npm.cmd run lint
```