from __future__ import annotations

from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from frontend.components.api import APIError, delete, get, post, set_session_id
from frontend.components.charts import build_figure
from frontend.components.exports import rows_to_csv, rows_to_xlsx
from frontend.styles.theme import THEME_CSS

st.set_page_config(
    page_title="QueryMind AI", page_icon="◈", layout="wide", initial_sidebar_state="expanded"
)
st.markdown(THEME_CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "provider": "gemini",
        "model": "",
        "api_key": "",
        "base_url": "",
        "temperature": 0.1,
        "max_tokens": 1000,
        "generation": None,
        "validation": None,
        "result": None,
        "question": "",
        "conversation": [],
        "active_database": "demo",
        "correction_attempts": 0,
        "analysis_id": None,
        "ai_summary": True,
        "provider_profiles": {},
        "discovered_models_by_provider": {},
        "api_session_id": uuid4().hex,
        "public_demo_mode": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    set_session_id(st.session_state.api_session_id)


def provider_payload() -> dict[str, Any] | None:
    profile = st.session_state.provider_profiles.get(st.session_state.provider, {})
    model = profile.get("model", "")
    if not model:
        return None
    return {
        "provider": st.session_state.provider,
        "model": model,
        "api_key": profile.get("api_key") or None,
        "base_url": profile.get("base_url") or None,
        "temperature": st.session_state.temperature,
        "max_tokens": st.session_state.max_tokens,
    }


@st.cache_data(show_spinner=False)
def result_as_xlsx(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    return rows_to_xlsx(rows, columns)


def choose_discovered_model(provider: str) -> None:
    selected = st.session_state.get(f"discovered_select_{provider}", "")
    if selected:
        model = selected.removeprefix("models/")
        st.session_state.provider_profiles.setdefault(provider, {})["model"] = model
        widget_key = st.session_state.get("active_model_widget_key")
        if widget_key:
            st.session_state[widget_key] = model
        st.session_state.model = model


def load_followup(question: str) -> None:
    st.session_state.question = question
    st.session_state.generation = None
    st.session_state.validation = None
    st.session_state.result = None
    st.session_state.pop("insight", None)


def safe_call(callable_, *args: Any, **kwargs: Any) -> Any:
    try:
        return callable_(*args, **kwargs)
    except APIError as exc:
        st.error(str(exc))
        return None


def hero(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="qm-hero"><div class="qm-kicker">{kicker}</div><h1>{title}</h1>'
        f'<div class="qm-subtle">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


def database_options() -> tuple[list[dict[str, Any]], dict[str, str]]:
    response = safe_call(get, "/databases") or {"databases": []}
    databases = response["databases"]
    labels = {item["id"]: f"{item['name']} · {item['dialect']}" for item in databases}
    return databases, labels


def overview_page() -> None:
    hero(
        "Workspace",
        "Your analytics command center",
        "Live activity from your local QueryMind workspace.",
    )
    data = safe_call(get, "/overview")
    if not data:
        return
    stats = data["stats"]
    cols = st.columns(4)
    values = [
        ("Executed queries", stats["executed_queries"]),
        ("Successful", stats["successful_queries"]),
        ("Average runtime", f"{stats['average_execution_ms']:.0f} ms"),
        ("Saved queries", stats["saved_queries"]),
    ]
    for column, (label, value) in zip(cols, values, strict=True):
        column.markdown(
            f'<div class="qm-card"><div class="qm-card-label">{label}</div><div class="qm-card-value">{value}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown("### Recent queries")
    if data["recent_queries"]:
        frame = pd.DataFrame(data["recent_queries"])
        st.dataframe(
            frame[["created_at", "question", "status", "row_count", "execution_time_ms"]],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No queries yet. Open **Ask Your Data** to run the first analysis.")
    st.markdown("### Workspace status")
    left, right = st.columns(2)
    left.markdown(
        f'<div class="qm-card"><div class="qm-card-label">Active database</div><div class="qm-card-value">'
        f"{next((d['name'] for d in data['databases'] if d['id'] == st.session_state.active_database), 'None')}</div></div>",
        unsafe_allow_html=True,
    )
    configured = bool(provider_payload())
    right.markdown(
        f'<div class="qm-card"><div class="qm-card-label">AI provider</div><div class="qm-card-value">'
        f"{st.session_state.provider.title() if configured else 'Not configured'}</div></div>",
        unsafe_allow_html=True,
    )


def execute_validated(question: str) -> None:
    validation = st.session_state.validation
    if not validation or not validation.get("valid"):
        st.error("Validate the SQL before running it.")
        return
    payload = {
        "validation_id": validation["validation_id"],
        "question": question,
        "provider": st.session_state.provider if provider_payload() else None,
        "model": (provider_payload() or {}).get("model"),
    }
    try:
        with st.spinner("Running the validated read-only query…"):
            result = post("/query/execute", payload)
        st.session_state.result = result
        st.session_state.validation = None
        st.session_state.conversation.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": f"SQL: {st.session_state.generation['sql']}"},
            ]
        )
        st.session_state.correction_attempts = 0
    except APIError as exc:
        st.session_state.execution_error = str(exc)
        st.error(str(exc))


def results_panel() -> None:
    result = st.session_state.result
    if not result:
        return
    st.divider()
    top = st.columns([1, 1, 1, 2])
    top[0].metric("Rows", result["row_count"])
    top[1].metric("Runtime", f"{result['execution_time_ms']:.1f} ms")
    top[2].metric("Status", "Truncated" if result["truncated"] else "Complete")
    top[3].caption(f"Query ID: {result['query_id']}")
    tabs = st.tabs(["Results", "Visualization", "Insights", "Export"])
    frame = pd.DataFrame(result["rows"], columns=result["columns"])
    with tabs[0]:
        st.dataframe(frame, width="stretch", hide_index=True)
    with tabs[1]:
        recommendation = result["chart"]
        chart_types = [
            "bar",
            "horizontal_bar",
            "line",
            "area",
            "scatter",
            "pie",
            "histogram",
            "table",
        ]
        default = recommendation["type"] if recommendation["type"] in chart_types else "table"
        selected = st.selectbox("Chart type", chart_types, index=chart_types.index(default))
        figure = build_figure(
            frame,
            recommendation,
            selected,
            st.session_state.question or "Query results",
        )
        if figure:
            figure.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(figure, width="stretch")
        else:
            st.dataframe(frame, width="stretch", hide_index=True)
        st.caption(f"Recommendation: {recommendation['reason']}")
    with tabs[2]:
        st.markdown(result["summary"])
        if st.session_state.ai_summary and provider_payload():
            if st.button("Generate AI insight", key="ai-insight"):
                response = safe_call(
                    post,
                    "/query/explain",
                    {
                        "question": st.session_state.question,
                        "columns": result["columns"],
                        "rows": result["rows"],
                        "provider": provider_payload(),
                    },
                )
                if response:
                    st.session_state.insight = response["explanation"]
            if st.session_state.get("insight"):
                st.markdown(st.session_state.insight)
        st.caption(
            "AI summaries receive only the displayed columns and a bounded row sample; credentials are never sent in prompts."
        )
    with tabs[3]:
        csv_data = rows_to_csv(result["rows"], result["columns"])
        excel = result_as_xlsx(result["rows"], result["columns"])
        c1, c2, c3 = st.columns(3)
        c1.download_button(
            "Download CSV", csv_data, "querymind-results.csv", "text/csv", width="stretch"
        )
        c2.download_button(
            "Download XLSX",
            excel,
            "querymind-results.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
        c3.download_button(
            "Download SQL",
            st.session_state.generation["sql"],
            "querymind-query.sql",
            "text/sql",
            width="stretch",
        )
        if st.session_state.public_demo_mode:
            st.caption("Saving is disabled in the public demo to keep visitor sessions isolated.")
        else:
            with st.form("save-query-form"):
                name = st.text_input("Saved query name", value=st.session_state.question[:80])
                category = st.text_input("Category", value="General")
                if st.form_submit_button("Save query"):
                    response = safe_call(
                        post,
                        "/queries/saved",
                        {
                            "name": name,
                            "question": st.session_state.question,
                            "sql": st.session_state.generation["sql"],
                            "database_id": st.session_state.active_database,
                            "category": category,
                        },
                    )
                    if response:
                        st.success("Query saved. Results were not stored.")
    followups = result.get("followups", [])
    if followups:
        st.markdown("### Continue your analysis")
        st.caption("Choose a follow-up; your recent question and SQL context will be preserved.")
        columns = st.columns(len(followups))
        for column, suggestion in zip(columns, followups, strict=True):
            column.button(
                suggestion,
                key=f"followup-{result['query_id']}-{suggestion}",
                on_click=load_followup,
                args=(suggestion,),
                width="stretch",
            )


def ask_page() -> None:
    hero(
        "Natural-language analytics",
        "Ask your data anything",
        "Generate, inspect, approve, and run safe read-only SQL.",
    )
    databases, labels = database_options()
    if not databases:
        st.warning("No database connections are available.")
        return
    ids = list(labels)
    if st.session_state.active_database not in ids:
        st.session_state.active_database = ids[0]
    top_left, top_right = st.columns([2, 1])
    with top_left:
        selected = st.selectbox(
            "Database",
            ids,
            index=ids.index(st.session_state.active_database),
            format_func=labels.get,
        )
        st.session_state.active_database = selected
    with top_right:
        mode = st.segmented_control(
            "Execution mode",
            ["Manual approval", "Auto after validation"],
            default="Manual approval",
        )
    examples = safe_call(get, "/query/examples") or {"examples": []}
    with st.expander("Try a deterministic example — no AI key required"):
        st.caption("These are curated SQL examples, not AI-generated answers.")
        columns = st.columns(2)
        for index, example in enumerate(examples["examples"]):
            if columns[index % 2].button(
                example["question"], key=f"example-{index}", width="stretch"
            ):
                st.session_state.question = example["question"]
                st.session_state.generation = {
                    "sql": example["sql"],
                    "explanation": "Curated demo query using the actual demo schema.",
                    "referenced_tables": [],
                    "assumptions": ["Completed orders represent realized revenue."],
                    "suggested_chart": "table",
                }
                st.session_state.validation = safe_call(
                    post, "/query/validate", {"sql": example["sql"], "database_id": selected}
                )
                st.session_state.result = None
                st.rerun()
    question = st.text_area(
        "What would you like to know?",
        key="question",
        height=105,
        placeholder="e.g. Show the top 10 products by revenue and compare their sales volume",
    )
    action_cols = st.columns([1, 1, 3])
    if action_cols[0].button("Generate SQL", type="primary", width="stretch"):
        config = provider_payload()
        if not config:
            st.warning("Choose a model in AI Settings, or use a labeled example above.")
        elif question.strip():
            with st.spinner("Selecting relevant schema and generating SQL…"):
                response = safe_call(
                    post,
                    "/query/generate",
                    {
                        "question": question,
                        "database_id": selected,
                        "provider": config,
                        "conversation": st.session_state.conversation[-6:],
                    },
                )
            if response:
                st.session_state.generation = response["generation"]
                st.session_state.analysis_id = response["analysis_id"]
                st.session_state.llm_usage = response.get("usage")
                st.session_state.validation = response["validation"]
                st.session_state.result = None
                st.session_state.pop("insight", None)
                if (
                    mode == "Auto after validation"
                    and response["validation"]
                    and response["validation"]["valid"]
                ):
                    execute_validated(question)
                st.rerun()
    if action_cols[1].button("New analysis", width="stretch"):
        for key in ("generation", "validation", "result", "insight", "execution_error"):
            st.session_state[key] = None
        st.session_state.question = ""
        st.session_state.conversation = []
        st.rerun()
    generation = st.session_state.generation
    if generation:
        if generation.get("clarification_needed"):
            st.warning(generation["clarification_needed"])
        if generation.get("sql"):
            st.markdown("### SQL preview")
            st.code(generation["sql"], language="sql", line_numbers=True)
            st.caption(generation.get("explanation", ""))
            if st.session_state.get("llm_usage"):
                st.caption(f"Provider usage: {st.session_state.llm_usage}")
            validation = st.session_state.validation
            if validation and validation.get("valid"):
                st.success("Passed structural, read-only, function, table, and schema validation.")
                if st.button("Run Query", type="primary", disabled=mode == "Auto after validation"):
                    execute_validated(question)
                    st.rerun()
            elif validation:
                st.error("Validation blocked this SQL: " + " ".join(validation.get("errors", [])))
    can_correct = (
        st.session_state.get("execution_error")
        and provider_payload()
        and st.session_state.correction_attempts < 2
    )
    if can_correct and st.button("Ask AI to propose a correction"):
        st.session_state.correction_attempts += 1
        corrected = safe_call(
            post,
            "/query/correct",
            {
                "analysis_id": st.session_state.analysis_id,
                "question": question,
                "sql": generation["sql"],
                "error": st.session_state.execution_error,
                "database_id": selected,
                "provider": provider_payload(),
            },
        )
        if corrected:
            st.session_state.generation = corrected["generation"]
            st.session_state.validation = corrected["validation"]
            st.session_state.execution_error = None
            st.info("A corrected query is ready. Review and approve it before execution.")
            st.rerun()
    results_panel()


def database_page() -> None:
    hero(
        "Data sources",
        "Database connections",
        "Credentials stay server-side in memory and are never included in AI prompts.",
    )
    databases, _ = database_options()
    for item in databases:
        with st.expander(
            f"{'●' if item['status'] == 'connected' else '○'}  {item['name']} · {item['dialect']}",
            expanded=item["is_demo"],
        ):
            st.caption(
                "Built-in read-only demo" if item["is_demo"] else f"Connection ID: {item['id']}"
            )
            schema = safe_call(get, f"/databases/{item['id']}/schema")
            if schema:
                refresh_col, count_col = st.columns([1, 3])
                count_col.write(f"**{len(schema['tables'])} tables**")
                if refresh_col.button("Refresh schema", key=f"refresh-{item['id']}"):
                    safe_call(get, f"/databases/{item['id']}/schema", refresh=True)
                    st.rerun()
                for table in schema["tables"]:
                    columns = ", ".join(f"{c['name']} ({c['type']})" for c in table["columns"])
                    st.markdown(f"- `{table['name']}` — {columns}")
                    if st.button(
                        f"Preview {table['name']}", key=f"preview-{item['id']}-{table['name']}"
                    ):
                        preview = safe_call(get, f"/databases/{item['id']}/preview/{table['name']}")
                        if preview:
                            st.dataframe(preview["rows"], width="stretch", hide_index=True)
            if not item["is_demo"] and st.button("Remove connection", key=f"remove-{item['id']}"):
                safe_call(delete, f"/databases/{item['id']}")
                st.rerun()
    st.markdown("### Add a connection")
    with st.form("database-connect"):
        name = st.text_input("Connection name")
        dialect = st.selectbox("Database type", ["postgresql", "sqlite"])
        url = st.text_input(
            "SQLAlchemy database URL",
            type="password",
            placeholder="postgresql+psycopg://readonly_user:password@localhost/analytics",
        )
        schemas = st.text_input(
            "Allowed schemas", value="public" if dialect == "postgresql" else ""
        )
        st.caption(
            "Use a dedicated read-only PostgreSQL role. SQLite files are reopened in read-only mode."
        )
        test, connect = st.columns(2)
        if test.form_submit_button("Test connection", width="stretch"):
            response = safe_call(post, "/databases/test", {"dialect": dialect, "database_url": url})
            if response:
                st.success("Connection succeeded.")
        if connect.form_submit_button("Save for this session", type="primary", width="stretch"):
            response = safe_call(
                post,
                "/databases/connect",
                {
                    "name": name,
                    "dialect": dialect,
                    "database_url": url,
                    "allowed_schemas": [s.strip() for s in schemas.split(",") if s.strip()],
                },
            )
            if response:
                st.success(
                    "Connection added. Its credentials will be forgotten when the server stops."
                )
                st.rerun()


def history_page() -> None:
    hero(
        "Audit trail",
        "Query history",
        "Review real execution outcomes without retaining result data.",
    )
    search = st.text_input("Search questions")
    response = safe_call(get, "/query/history", search=search or None, limit=500)
    if not response or not response["history"]:
        st.info("No matching history entries.")
        return
    frame = pd.DataFrame(response["history"])
    status = st.multiselect("Status", sorted(frame["status"].dropna().unique()), default=[])
    if status:
        frame = frame[frame["status"].isin(status)]
    st.dataframe(frame, width="stretch", hide_index=True)
    st.download_button(
        "Export history CSV", frame.to_csv(index=False), "querymind-history.csv", "text/csv"
    )


def saved_page() -> None:
    hero(
        "Reusable analysis",
        "Saved queries",
        "Saved definitions are revalidated every time before they can run.",
    )
    response = safe_call(get, "/queries/saved")
    if not response or not response["saved_queries"]:
        st.info("Save a query from the results panel to see it here.")
        return
    for item in response["saved_queries"]:
        with st.expander(f"{item['name']} · {item['category']}"):
            st.write(item["question"])
            st.code(item["sql"], language="sql")
            c1, c2 = st.columns(2)
            if c1.button("Validate and prepare", key=f"rerun-{item['id']}"):
                validation = safe_call(
                    post,
                    "/query/validate",
                    {"sql": item["sql"], "database_id": item["database_id"]},
                )
                if validation and validation["valid"]:
                    st.session_state.question = item["question"]
                    st.session_state.generation = {
                        "sql": item["sql"],
                        "explanation": "Loaded from saved queries.",
                    }
                    st.session_state.validation = validation
                    st.success("Prepared safely. Open Ask Your Data to review and run it.")
            if c2.button("Delete", key=f"delete-{item['id']}"):
                safe_call(delete, f"/queries/saved/{item['id']}")
                st.rerun()


def ai_settings_page() -> None:
    hero(
        "Model control",
        "AI Settings",
        "Bring one provider key. QueryMind never falls back to another provider automatically.",
    )
    info = safe_call(get, "/providers")
    profiles = st.session_state.provider_profiles
    if info and not profiles and info.get("default_model"):
        st.session_state.provider = info.get("default_provider") or st.session_state.provider
        profiles.setdefault(st.session_state.provider, {})["model"] = info["default_model"]
    if info:
        st.markdown(
            '<div class="qm-notice">Free-tier availability and quotas can change. QueryMind displays provider metadata when available but never assumes a model is free.</div>',
            unsafe_allow_html=True,
        )
    provider_options = [item["id"] for item in info.get("providers", [])] if info else []
    provider_options = provider_options or ["gemini", "groq", "openrouter", "custom", "ollama"]
    if st.session_state.provider not in provider_options:
        st.session_state.provider = provider_options[0]
    provider = st.selectbox(
        "Provider",
        provider_options,
        index=provider_options.index(st.session_state.provider),
    )
    st.session_state.provider = provider
    profile = profiles.setdefault(provider, {})
    if st.session_state.get("settings_rendered_provider") != provider:
        st.session_state.settings_widget_generation = (
            st.session_state.get("settings_widget_generation", 0) + 1
        )
        st.session_state.settings_rendered_provider = provider
    generation = st.session_state.get("settings_widget_generation", 1)
    base_url_key = f"base_url_widget_{provider}_{generation}"
    api_key_key = f"api_key_widget_{provider}_{generation}"
    model_key = f"model_widget_{provider}_{generation}"
    st.session_state.active_model_widget_key = model_key
    if provider in {"custom", "ollama"}:
        default_url = profile.get("base_url", "") or (
            "http://localhost:11434" if provider == "ollama" else ""
        )
        base_url = st.text_input("API base URL", value=default_url, key=base_url_key)
    else:
        base_url = ""
    if provider != "ollama":
        api_key = st.text_input(
            "API key",
            type="password",
            value=profile.get("api_key", ""),
            key=api_key_key,
            help="Kept only in this Streamlit session. Use .env for persistent local configuration.",
        )
    else:
        api_key = ""
    model = st.text_input(
        "Model identifier",
        value=profile.get("model", ""),
        key=model_key,
        placeholder="Select Discover models or enter a provider model ID",
    )
    left, right = st.columns(2)
    st.session_state.temperature = left.slider(
        "Temperature", 0.0, 1.5, float(st.session_state.temperature), 0.1
    )
    st.session_state.max_tokens = right.slider(
        "Maximum output tokens", 128, 4096, int(st.session_state.max_tokens), 128
    )
    profile.update({"api_key": api_key, "base_url": base_url, "model": model})
    st.session_state.provider_profiles = {
        **profiles,
        provider: dict(profile),
    }
    # Compatibility mirrors for status cards and existing sessions. Payloads use isolated profiles.
    st.session_state.api_key = api_key
    st.session_state.base_url = base_url
    st.session_state.model = model
    buttons = st.columns(2)
    if buttons[0].button("Discover models", width="stretch"):
        config = {
            "provider": st.session_state.provider,
            "model": model or "model-discovery",
            "api_key": api_key or None,
            "base_url": base_url or None,
            "temperature": st.session_state.temperature,
            "max_tokens": st.session_state.max_tokens,
        }
        response = safe_call(post, "/providers/models", config)
        if response:
            st.session_state.discovered_models_by_provider[provider] = response["models"]
    if buttons[1].button("Test connection", type="primary", width="stretch"):
        config = provider_payload()
        if config and safe_call(post, "/providers/test", config):
            st.success("Provider connection succeeded.")
    models = st.session_state.discovered_models_by_provider.get(provider, [])
    if models:
        options = [item.get("id") or item.get("name") for item in models]
        selected = st.selectbox("Available models", options, key=f"discovered_select_{provider}")
        details = next(
            (item for item in models if (item.get("id") or item.get("name")) == selected), {}
        )
        st.button(
            "Use selected model",
            on_click=choose_discovered_model,
            args=(provider,),
        )
        if provider == "openrouter":
            st.caption(
                "Free"
                if details.get("is_free")
                else f"Pricing metadata: {details.get('pricing', 'unavailable')}"
            )
    st.divider()
    st.checkbox("Generate optional AI result summaries", key="ai_summary")
    st.caption(
        "Settings switch immediately. Raw keys are never returned by the backend or written to query history."
    )


def about_page() -> None:
    hero("About", "QueryMind AI", "Ask Your Data Anything.")
    st.markdown(
        """
QueryMind AI is a local-first analytics workspace that turns natural-language questions into reviewable SQL,
executes only validated read-only statements, and creates interactive visual explanations.

**Security model**

- SQLGlot AST validation, one-statement enforcement, allowlisted tables and schemas, dangerous-function blocking.
- Server-held, expiring validation tickets; manual approval by default.
- Read-only SQLite connections and transactions; PostgreSQL read-only transaction plus statement timeout.
- Credentials excluded from prompts, logs, history, and API responses.

Before any public deployment, add authentication, TLS, per-user authorization, a secrets manager, network policy,
and database audit controls. This application binds to localhost by default.
        """
    )
    st.markdown("[Open API documentation](http://127.0.0.1:8000/docs)")


init_state()
with st.sidebar:
    st.markdown(
        '<div class="qm-brand">QueryMind <span>AI</span></div><div class="qm-subtle">Turn Questions Into Insights.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    try:
        health = get("/health")
        st.session_state.public_demo_mode = health.get("mode") == "public_demo"
        st.markdown('<span class="qm-status">● API connected</span>', unsafe_allow_html=True)
    except APIError:
        st.error("API offline")
    pages = (
        ["Overview", "Ask Your Data", "AI Settings", "About"]
        if st.session_state.public_demo_mode
        else [
            "Overview",
            "Ask Your Data",
            "Database Connections",
            "Query History",
            "Saved Queries",
            "AI Settings",
            "About",
        ]
    )
    page = st.radio("Navigation", pages, label_visibility="collapsed")
    st.markdown("---")
    st.caption(
        "Restricted public demo" if st.session_state.public_demo_mode else "Local single-user mode"
    )

{
    "Overview": overview_page,
    "Ask Your Data": ask_page,
    "Database Connections": database_page,
    "Query History": history_page,
    "Saved Queries": saved_page,
    "AI Settings": ai_settings_page,
    "About": about_page,
}[page]()
