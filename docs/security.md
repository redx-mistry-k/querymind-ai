# Security model

## Trust boundaries

Language-model output, browser input, SQL text, custom provider URLs, and database errors are untrusted. QueryMind applies multiple independent controls because parsing alone is not a sufficient security boundary.

## SQL controls

1. Parse using the selected database dialect.
2. Require exactly one SELECT-based statement.
3. Reject DDL, DML, administrative statements, writable CTEs, `SELECT INTO`, and row locks.
4. Reject known file, extension, session, blocking, sequence-mutating, and administrative functions, including dangerous PostgreSQL function families.
5. Match base tables and explicit schemas against introspected allowlists; reject system schemas/tables.
6. Check qualified columns and single-table unqualified columns against introspected metadata.
7. Wrap the normalized query with a maximum-row limit.
8. Store validated SQL on the server behind an expiring, random, single-use ticket.
9. Execute only the server copy of the validated SQL, never SQL resubmitted with an approval flag.

There is intentionally no “disable validation” switch.

## Database controls

### SQLite

- User databases and the built-in demo are opened through `mode=ro` URI connections.
- `PRAGMA query_only = ON` is applied before execution.
- A progress handler interrupts work after the configured timeout.
- Extension loading is never enabled.
- Every transaction is rolled back.

### PostgreSQL

- Users are required to supply a dedicated read-only login.
- QueryMind executes `SET TRANSACTION READ ONLY`.
- `statement_timeout` is scoped to the transaction.
- `search_path` is restricted to configured, identifier-quoted schemas.
- Every transaction is rolled back.

The database role is the decisive boundary. Do not use an owner, administrator, or superuser.

## Secret handling

- `.env`, local data, logs, and Streamlit secrets are gitignored.
- API responses expose provider configuration status, never raw keys.
- UI-entered keys stay in the Streamlit session and are sent only to the localhost backend for the selected request.
- Database URLs exist only in backend memory and are not restored after restart.
- History stores provider/model names and query metadata, not credentials or result rows.
- Prompts exclude keys, passwords, URLs, and unrelated result data.
- Custom provider URLs reject embedded credentials, non-HTTP(S) schemes, and resolved private/link-local/reserved addresses. Localhost is allowed only for the explicit Ollama path or when the operator opts in for a custom local provider.

## Network and deployment

Development services bind to `127.0.0.1`. CORS accepts only configured frontend origins. This is a local, trusted, single-user profile—not an authenticated network service.

Phase 2 adds a fail-closed guard for accidental exposure: if `APP_HOST` is not a loopback address, application creation fails unless `QUERYMIND_API_TOKEN` is configured. When present, every `/api/v1` request requires the matching bearer token, and the Streamlit server attaches it to backend calls. This protects a backend shared with one trusted frontend service, but it does not provide individual user identity or per-user authorization.

The restricted `PUBLIC_DEMO_MODE` profile additionally requires the service token even on loopback, disables OpenAPI documentation, external database creation/testing/removal, custom endpoints, Ollama, shared history, and saved-query APIs. It accepts only the fictional `demo` database, applies stricter row and duration caps, and rate-limits all requests, LLM-related requests, and executions by an opaque Streamlit session identifier. The limiter is intentionally single-process and resets when the service restarts; it is a portfolio-demo control, not a distributed production quota system.

Before remote or multi-user deployment, add:

- authenticated sessions and per-user/tenant authorization;
- TLS and secure proxy/header configuration;
- managed secrets, rotation, and database certificate validation;
- CSRF protection where cookie authentication is introduced;
- outbound egress restrictions and DNS rebinding defenses at the network layer;
- persistent audit policy, privacy review, and retention controls;
- worker-safe shared ticket and rate-limit storage for multi-worker deployments.

## Data sent to AI providers

SQL generation may send selected schema names, selected column names/types, relationships, the question, and bounded conversation context to the provider explicitly chosen by the user. Optional AI explanations may send column names, deterministic statistics, and up to 50 returned rows. Disable AI summaries to avoid the second request.

Do not use cloud providers with sensitive schemas or records until organizational data-processing, residency, retention, and vendor policies have been reviewed.

## Limitations

- A denylist cannot prove that every user-defined function is side-effect free.
- SQL parsing cannot protect credentials that already have excessive permissions.
- Query complexity can still consume resources within the timeout.
- Schema names and sampled rows can themselves be sensitive.
- In-memory validation tickets are process-local and unsuitable for multiple workers without shared TTL storage.
- SQLite is appropriate for the demo and local metadata, not untrusted multi-tenant workloads.

Report security issues privately to the repository owner rather than including sensitive details in a public issue.
