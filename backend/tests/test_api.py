def test_health_and_demo_database(client):
    assert client.get("/api/v1/health").status_code == 200
    databases = client.get("/api/v1/databases").json()["databases"]
    assert any(item["id"] == "demo" for item in databases)


def test_validate_execute_history_and_save(client):
    validation = client.post(
        "/api/v1/query/validate",
        json={
            "database_id": "demo",
            "sql": "SELECT status, COUNT(*) AS total FROM orders GROUP BY status",
        },
    ).json()
    assert validation["valid"]
    execution = client.post(
        "/api/v1/query/execute",
        json={"validation_id": validation["validation_id"], "question": "Orders by status"},
    )
    assert execution.status_code == 200
    assert execution.json()["row_count"] == 4
    assert (
        client.post(
            "/api/v1/query/execute",
            json={"validation_id": validation["validation_id"], "question": "Replay"},
        ).status_code
        == 400
    )
    history = client.get("/api/v1/query/history").json()["history"]
    assert any(item["question"] == "Orders by status" for item in history)
    saved = client.post(
        "/api/v1/queries/saved",
        json={
            "name": "Status counts",
            "question": "Orders by status",
            "sql": "SELECT status FROM orders",
            "database_id": "demo",
        },
    )
    assert saved.status_code == 201
    saved_id = saved.json()["id"]
    assert client.delete(f"/api/v1/queries/saved/{saved_id}").status_code == 200


def test_api_blocks_destructive_sql(client):
    response = client.post(
        "/api/v1/query/validate", json={"database_id": "demo", "sql": "DROP TABLE orders"}
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_examples_are_labeled_non_ai(client):
    response = client.get("/api/v1/query/examples").json()
    assert response["generated_by_ai"] is False
    assert len(response["examples"]) >= 4


def test_validation_ticket_cannot_be_forged_or_tampered(client):
    from backend.app.api.v1 import _validation_tickets

    assert (
        client.post(
            "/api/v1/query/execute",
            json={"validation_id": "0" * 32, "question": "Forged ticket"},
        ).status_code
        == 400
    )
    validation = client.post(
        "/api/v1/query/validate",
        json={"database_id": "demo", "sql": "SELECT COUNT(*) AS total FROM orders"},
    ).json()
    _validation_tickets[validation["validation_id"]]["digest"] = "0" * 64
    response = client.post(
        "/api/v1/query/execute",
        json={"validation_id": validation["validation_id"], "question": "Tampered ticket"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_validation"


def test_history_and_saved_queries_persist_across_restart(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.core.config import Settings
    from backend.app.main import create_app

    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        demo_db_path=tmp_path / "data" / "demo" / "querymind_demo.db",
        metadata_db_path=tmp_path / "data" / "querymind.db",
    )
    with TestClient(create_app(settings)) as first:
        validation = first.post(
            "/api/v1/query/validate",
            json={"database_id": "demo", "sql": "SELECT COUNT(*) AS total FROM orders"},
        ).json()
        assert (
            first.post(
                "/api/v1/query/execute",
                json={"validation_id": validation["validation_id"], "question": "Persistent count"},
            ).status_code
            == 200
        )
        assert (
            first.post(
                "/api/v1/queries/saved",
                json={
                    "name": "Persistent query",
                    "question": "Count orders",
                    "sql": "SELECT COUNT(*) AS total FROM orders",
                    "database_id": "demo",
                },
            ).status_code
            == 201
        )
    with TestClient(create_app(settings)) as restarted:
        history = restarted.get("/api/v1/query/history").json()["history"]
        saved = restarted.get("/api/v1/queries/saved").json()["saved_queries"]
        assert any(item["question"] == "Persistent count" for item in history)
        assert any(item["name"] == "Persistent query" for item in saved)


def test_remote_bind_requires_api_token(tmp_path):
    import pytest
    from fastapi.testclient import TestClient

    from backend.app.core.config import Settings
    from backend.app.main import create_app

    base = {
        "app_host": "0.0.0.0",
        "root_dir": tmp_path,
        "data_dir": tmp_path / "data",
        "demo_db_path": tmp_path / "data" / "demo" / "querymind_demo.db",
        "metadata_db_path": tmp_path / "data" / "querymind.db",
    }
    with pytest.raises(RuntimeError, match="QUERYMIND_API_TOKEN"):
        create_app(Settings(**base))
    protected = create_app(Settings(**base, api_access_token="test-secret"))
    with TestClient(protected) as secured:
        assert secured.get("/api/v1/health").status_code == 401
        assert (
            secured.get(
                "/api/v1/health", headers={"Authorization": "Bearer test-secret"}
            ).status_code
            == 200
        )


def test_public_demo_requires_token_even_on_loopback(tmp_path):
    import pytest

    from backend.app.core.config import Settings
    from backend.app.main import create_app

    with pytest.raises(RuntimeError, match="QUERYMIND_API_TOKEN"):
        create_app(
            Settings(
                public_demo_mode=True,
                root_dir=tmp_path,
                data_dir=tmp_path / "data",
                demo_db_path=tmp_path / "data" / "demo" / "querymind_demo.db",
                metadata_db_path=tmp_path / "data" / "querymind.db",
            )
        )


def test_public_demo_restricts_connections_metadata_and_rows(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.core.config import Settings
    from backend.app.main import create_app

    settings = Settings(
        public_demo_mode=True,
        api_access_token="public-test-token",
        public_demo_max_query_rows=7,
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        demo_db_path=tmp_path / "data" / "demo" / "querymind_demo.db",
        metadata_db_path=tmp_path / "data" / "querymind.db",
    )
    headers = {
        "Authorization": "Bearer public-test-token",
        "X-QueryMind-Session": "public-test-session-01",
    }
    with TestClient(create_app(settings)) as public:
        assert public.get("/api/v1/health").status_code == 401
        health = public.get("/api/v1/health", headers=headers).json()
        assert health == {"status": "ok", "app": "QueryMind AI", "mode": "public_demo"}
        assert public.get("/docs", headers=headers).status_code == 404
        provider_ids = {
            item["id"]
            for item in public.get("/api/v1/providers", headers=headers).json()["providers"]
        }
        assert provider_ids == {"gemini", "groq", "openrouter"}
        assert (
            public.post(
                "/api/v1/databases/test",
                headers=headers,
                json={"dialect": "sqlite", "database_url": "sqlite:///private.db"},
            ).status_code
            == 403
        )
        assert (
            public.post(
                "/api/v1/databases/connect",
                headers=headers,
                json={
                    "name": "private",
                    "dialect": "sqlite",
                    "database_url": "sqlite:///private.db",
                    "allowed_schemas": [],
                },
            ).status_code
            == 403
        )
        assert public.get("/api/v1/query/history", headers=headers).status_code == 403
        assert public.get("/api/v1/queries/saved", headers=headers).status_code == 403
        assert public.get("/api/v1/overview", headers=headers).json()["recent_queries"] == []
        blocked = public.post(
            "/api/v1/query/validate",
            headers=headers,
            json={"database_id": "other", "sql": "SELECT 1"},
        )
        assert blocked.status_code == 403
        validation = public.post(
            "/api/v1/query/validate",
            headers=headers,
            json={"database_id": "demo", "sql": "SELECT * FROM customers ORDER BY id"},
        ).json()
        execution = public.post(
            "/api/v1/query/execute",
            headers=headers,
            json={"validation_id": validation["validation_id"], "question": "Customers"},
        ).json()
        assert execution["row_count"] == 7
        assert execution["truncated"] is True


def test_public_demo_limits_llm_calls_per_session(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.core.config import Settings
    from backend.app.main import create_app

    settings = Settings(
        public_demo_mode=True,
        api_access_token="public-test-token",
        public_demo_llm_calls_per_minute=1,
        public_demo_llm_calls_per_session=1,
        gemini_api_key="",
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        demo_db_path=tmp_path / "data" / "demo" / "querymind_demo.db",
        metadata_db_path=tmp_path / "data" / "querymind.db",
    )
    headers = {
        "Authorization": "Bearer public-test-token",
        "X-QueryMind-Session": "rate-limit-session-01",
    }
    payload = {"provider": "gemini", "model": "gemini-test"}
    with TestClient(create_app(settings)) as public:
        assert (
            public.post("/api/v1/providers/models", headers=headers, json=payload).status_code
            == 400
        )
        limited = public.post("/api/v1/providers/models", headers=headers, json=payload)
        assert limited.status_code == 429
        assert limited.headers["retry-after"]
        assert limited.json()["detail"]["code"] == "demo_rate_limit"
