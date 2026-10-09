# QueryMind AI

**Ask Your Data Anything.**

QueryMind AI is a local-first, full-stack generative AI analytics application. It turns natural-language questions into reviewable SQL, validates every statement against a read-only security policy, executes it against SQLite or PostgreSQL, and renders interactive results with plain-English insights.

It is designed as a portfolio-quality reference implementation—not a chatbot wrapper. The FastAPI backend owns credentials, schema discovery, validation tickets, execution, history, and saved queries; Streamlit is a separate API client.

> Status: the SQLite demo workflow and automated provider mocks are verified. Gemini authentication and model discovery were verified against the configured project; live generation remains pending explicit confirmation of that project's billing tier. Optional PostgreSQL integration requires a user-supplied test server.

## Highlights

- Provider-independent adapters for Google Gemini, Groq, OpenRouter, custom OpenAI-compatible APIs, and optional local Ollama.
- Runtime model discovery, explicit model selection, quota/rate-limit messages, no automatic provider fallback, and OpenRouter pricing metadata.
- Schema-aware SQL generation with compact relevant-table selection and bounded conversation context.
- SQLGlot AST validation, single-statement enforcement, DDL/DML and writable-CTE rejection, table/schema/column allowlists, dangerous-function checks, and row-lock rejection.
- Opaque, expiring, single-use server-side validation tickets. Manual approval is the default; auto mode still requires every security check to pass.
- Database-level read-only controls: SQLite URI read-only access plus `query_only`; PostgreSQL read-only transactions, restricted search path, and statement timeout.
- Deterministic demo commerce database with 800 customers, 5,000 orders, and more than 10,000 order lines.
- Plotly chart recommendations, deterministic Pandas summaries, optional AI insights, CSV/XLSX/SQL downloads, and browser chart-image export.
- Query history, saved queries, revalidation on rerun, contextual follow-ups, and at most two UI-assisted SQL correction attempts.
- Structured error responses, secret-safe logging boundaries, restricted CORS, and localhost-only defaults.

## Product tour

The sidebar contains Overview, Ask Your Data, Database Connections, Query History, Saved Queries, AI Settings, and About.

The overview below was captured from the locally verified application after the Phase 2 UI smoke test:

![QueryMind AI overview dashboard](docs/images/overview.png)

No additional screenshots are claimed until their workflows have been exercised and captured.

## Architecture

```mermaid
flowchart LR
    U[Streamlit dashboard] -->|localhost REST| A[FastAPI /api/v1]
    A --> S[Schema selector]
    S --> L[Selected LLM provider]
    L --> P[Pydantic structured SQL]
    P --> V[SQLGlot validator]
    V --> T[(Expiring validation ticket)]
    T -->|manual approval or auto policy| E[Read-only executor]
    E --> D[(SQLite / PostgreSQL)]
    E --> R[Rows + timing]
    R --> C[Pandas + Plotly]
    R --> H[(Local history metadata)]
```

See [docs/architecture.md](docs/architecture.md) for the detailed sequence and [docs/security.md](docs/security.md) for the threat model and limitations.

## Technology

- Python 3.12+, FastAPI, Pydantic v2, Uvicorn, HTTPX
- SQLAlchemy 2.x, SQLGlot, SQLite, PostgreSQL/psycopg
- Streamlit, Plotly, Pandas, OpenPyXL
- Pytest, Ruff, GitHub Actions

## Quick start — Windows PowerShell

Install Python 3.12 or newer, then run:

```powershell
cd D:\path\to\QueryMindAi
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

`run.py` starts both services, opens the dashboard, streams their logs, and stops both on Ctrl+C.

- Dashboard: <http://127.0.0.1:8501>
- API docs: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/v1/health>

The helper below performs the environment setup but does not edit `.env`:

```powershell
.\scripts\setup.ps1
```

If PowerShell blocks activation, use this process-scoped setting:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Quick start — Linux/macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python run.py
```

## Run services independently

Backend:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend in another terminal:

```powershell
python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

## Configure one AI provider

Only one provider is needed. Either enter a key temporarily on **AI Settings**, or put one key in `.env`:

```dotenv
GEMINI_API_KEY=your_key_here
DEFAULT_AI_PROVIDER=gemini
DEFAULT_AI_MODEL=your_available_model_id
```

Equivalent variables are `GROQ_API_KEY` and `OPENROUTER_API_KEY`. For a custom provider, also configure `CUSTOM_LLM_BASE_URL` and `CUSTOM_LLM_MODEL`. Restart after changing `.env`; settings changed in the UI take effect immediately.

Use **Discover models** and choose a model returned for your own account. Free-tier eligibility, quotas, and model availability are provider-controlled and can change. QueryMind never silently changes providers or upgrades to a paid model. OpenRouter models are marked free only when its returned prompt and completion pricing are both zero.

See [docs/llm-providers.md](docs/llm-providers.md) for provider-specific details. The implementation follows the official [Gemini API](https://ai.google.dev/api), [Groq OpenAI compatibility](https://console.groq.com/docs/openai), [OpenRouter model API](https://openrouter.ai/docs/api/api-reference/models/get-models), and [Ollama compatibility API](https://docs.ollama.com/api/openai-compatibility).

## Demo mode

No database or AI key is required for the deterministic example workflow:

1. Start the application.
2. Open **Ask Your Data** and keep **QueryMind Demo** selected.
3. Expand **Try a deterministic example — no AI key required**.
4. Choose a curated example, review the SQL, and select **Run Query**.

The example SQL is clearly labeled as curated—not generated by AI. An AI key is required for arbitrary natural-language SQL and optional AI summaries.

Useful questions after configuring a provider:

- Show the top 10 products by revenue.
- Show monthly revenue trends.
- Which region generates the highest revenue?
- What is the average order value?
- Which customers have spent the most?
- Compare revenue across product categories.
- How many orders were placed each month?
- What percentage of orders were cancelled?

## PostgreSQL

Create a dedicated login with the least privileges necessary. An illustrative starting point (adapt schemas and tables to your environment):

```sql
CREATE ROLE querymind_reader LOGIN PASSWORD 'use-a-secret-manager';
GRANT CONNECT ON DATABASE analytics TO querymind_reader;
GRANT USAGE ON SCHEMA public TO querymind_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO querymind_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO querymind_reader;
ALTER ROLE querymind_reader SET default_transaction_read_only = on;
```

In **Database Connections**, use a SQLAlchemy URL such as:

```text
postgresql+psycopg://querymind_reader:PASSWORD@localhost:5432/analytics
```

The URL is held in backend memory for the current process and is not stored in metadata. Use TLS (`sslmode=require` or stronger) for non-local connections. Never use an administrator or superuser account.

## API summary

The interactive OpenAPI document at `/docs` is authoritative. Major routes include:

| Area | Routes |
|---|---|
| Health/providers | `GET /health`, `GET /providers`, `POST /providers/models`, `POST /providers/test` |
| Databases | `GET /databases`, `POST /databases/test`, `POST /databases/connect`, `GET /databases/{id}/schema` |
| Query lifecycle | `POST /query/generate`, `/validate`, `/execute`, `/correct`, `/explain` |
| Workspace | `GET /query/history`, `GET/POST /queries/saved`, `DELETE /queries/saved/{id}`, `GET /overview` |

All routes are below `/api/v1`.

## Tests and lint

```powershell
python -m pytest
python -m ruff check .
```

Phase 3 verification currently includes **62 passing tests**, a clean Ruff scan, a successful bytecode compilation pass, a seven-page Streamlit application harness, widget-driven demo validation/execution, FastAPI and Streamlit startup, and a genuine browser-rendered screenshot. Provider inference tests use mocks and consume no API quota. Gemini authentication/model discovery was verified live without sending a generation request; PostgreSQL still requires an external test database. The available local interpreter is Python 3.11.9, so the declared Python 3.12 deployment target still needs one CI or deployment smoke run.

## Project structure

```text
backend/app/
  api/                 versioned routes and service container
  core/                environment settings and logging
  models/              SQLAlchemy metadata models
  repositories/        history and saved-query persistence
  schemas/             Pydantic request/response contracts
  services/
    analytics/         chart choice and deterministic summaries
    database/          demo generation, introspection, read-only execution
    llm/               Gemini and OpenAI-compatible adapters
    sql/               prompt construction and SQL validation
backend/tests/          unit and API integration tests
frontend/               Streamlit dashboard, API client, custom theme
data/                   generated local databases (gitignored)
docs/                   architecture, security, deployment plan, screenshot
scripts/                setup, UI smoke test, screenshot capture
requirements-lock.txt   exact verified direct dependency versions
.python-version         declared local/CI Python series
.github/workflows/      CI tests and lint
run.py                  managed two-service launcher
```

## Security scope

QueryMind layers application validation over database read-only controls, but it is not a general SQL sandbox. Database credentials must themselves be least-privilege and read-only. The app is intended for trusted, local, single-user use and binds to localhost. Before exposing it to a network, add authentication, authorization, TLS, CSRF protections where applicable, a managed secrets store, egress policy, tenant isolation, audit retention, and deployment-specific database controls.

Phase 2 adds a fail-closed deployment guard: non-loopback API binding requires `QUERYMIND_API_TOKEN`, and the Streamlit server attaches that bearer token to backend calls. This is service-to-service protection, not a replacement for user identity, authorization, or rate limiting. See [docs/deployment-plan.md](docs/deployment-plan.md) before considering a public demo.

Schema and bounded result samples may be transmitted to the cloud provider selected by the user. Passwords, connection strings, API keys, and unrelated results are excluded. Disable AI summaries to avoid the second result-analysis request.

## Known limitations

- Live provider availability, billing/free-tier status, and quota behavior cannot be guaranteed or tested without the user's account.
- Database credentials are intentionally session-only; restart requires reconnecting unless configured by environment/infrastructure.
- PostgreSQL integration was not run locally because no PostgreSQL test server was supplied.
- The demo and metadata stores are single-user; multi-user deployments require per-user isolation and authentication.
- SQL function denylisting cannot prove arbitrary user-defined functions are side-effect free; the restricted database role is the primary boundary.
- Chart configuration is not persisted, and image downloads use Plotly's browser toolbar.

## Roadmap

- Authenticated multi-user deployment profile and external secrets manager.
- Optional PostgreSQL CI service integration.
- Persisted chart configurations and schema relationship visualization.
- Provider usage/cost dashboards where authoritative usage metadata is available.
- Pluggable semantic schema descriptions for very large warehouses.

## License

MIT. See [LICENSE](LICENSE).
