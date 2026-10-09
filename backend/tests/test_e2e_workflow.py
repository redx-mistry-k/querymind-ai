from __future__ import annotations

import json

from backend.app.services.llm.base import LLMProvider, LLMResponse


class ContextAwareMockProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(model="mock")
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages):
        self.calls.append(messages)
        question = messages[-1]["content"].lower()
        if "highest-revenue region" in question:
            sql = """
                WITH region_revenue AS (
                  SELECT r.id AS region_id, SUM(oi.quantity * oi.unit_price) AS region_revenue
                  FROM regions r JOIN customers c ON c.region_id = r.id
                  JOIN orders o ON o.customer_id = c.id
                  JOIN order_items oi ON oi.order_id = o.id
                  WHERE o.status = 'completed' GROUP BY r.id
                ), top_region AS (
                  SELECT region_id FROM region_revenue ORDER BY region_revenue DESC LIMIT 1
                )
                SELECT c.name AS customer,
                       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
                FROM customers c JOIN regions r ON r.id = c.region_id
                JOIN orders o ON o.customer_id = c.id
                JOIN order_items oi ON oi.order_id = o.id
                WHERE o.status = 'completed'
                  AND r.id = (SELECT region_id FROM top_region)
                GROUP BY c.id, c.name ORDER BY revenue DESC LIMIT 10
            """
            explanation = "Limits customers to the region with the greatest completed revenue."
            tables = ["regions", "customers", "orders", "order_items"]
        else:
            sql = """
                SELECT c.name AS customer,
                       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
                FROM customers c JOIN orders o ON o.customer_id = c.id
                JOIN order_items oi ON oi.order_id = o.id
                WHERE o.status = 'completed'
                GROUP BY c.id, c.name ORDER BY revenue DESC LIMIT 10
            """
            explanation = "Ranks customers by completed-order revenue."
            tables = ["customers", "orders", "order_items"]
        return LLMResponse(
            text=json.dumps(
                {
                    "sql": sql,
                    "explanation": explanation,
                    "referenced_tables": tables,
                    "assumptions": ["Completed orders represent realized revenue."],
                    "clarification_needed": None,
                    "suggested_chart": "horizontal_bar",
                }
            ),
            usage={"input_tokens": 200, "output_tokens": 120},
        )


def generate(client, question, conversation=None):
    return client.post(
        "/api/v1/query/generate",
        json={
            "question": question,
            "database_id": "demo",
            "provider": {
                "provider": "gemini",
                "model": "mock-model",
                "api_key": "mock-key",
            },
            "conversation": conversation or [],
        },
    )


def execute(client, generated, question):
    return client.post(
        "/api/v1/query/execute",
        json={
            "validation_id": generated["validation"]["validation_id"],
            "question": question,
            "provider": "gemini",
            "model": "mock-model",
        },
    )


def test_complete_contextual_ai_workflow(client, monkeypatch):
    from backend.app.api import v1

    provider = ContextAwareMockProvider()
    monkeypatch.setattr(v1, "_provider", lambda config, services: provider)
    first_question = "Show the top 10 customers by revenue."
    first_response = generate(client, first_question)
    assert first_response.status_code == 200
    first_generated = first_response.json()
    assert first_generated["usage"] == {"input_tokens": 200, "output_tokens": 120}
    assert first_generated["validation"]["valid"]
    assert set(first_generated["validation"]["referenced_tables"]) == {
        "customers",
        "orders",
        "order_items",
    }
    first_execution = execute(client, first_generated, first_question)
    assert first_execution.status_code == 200
    first_result = first_execution.json()
    assert first_result["row_count"] == 10
    assert first_result["chart"]["type"] == "horizontal_bar"
    assert "leading customer" in first_result["summary"].lower()
    assert first_result["followups"]
    saved = client.post(
        "/api/v1/queries/saved",
        json={
            "name": "Top customers",
            "question": first_question,
            "sql": first_generated["generation"]["sql"],
            "database_id": "demo",
            "category": "Revenue",
        },
    )
    assert saved.status_code == 201
    conversation = [
        {"role": "user", "content": first_question},
        {"role": "assistant", "content": f"SQL: {first_generated['generation']['sql']}"},
    ]
    followup_question = "Now show only customers from the highest-revenue region."
    followup_response = generate(client, followup_question, conversation)
    assert followup_response.status_code == 200
    followup_generated = followup_response.json()
    assert followup_generated["validation"]["valid"]
    assert any(
        item["role"] == "user" and item["content"] == first_question for item in provider.calls[-1]
    )
    followup_execution = execute(client, followup_generated, followup_question)
    assert followup_execution.status_code == 200
    assert followup_execution.json()["row_count"] == 10
    history = client.get("/api/v1/query/history", params={"search": "highest-revenue"}).json()
    assert any(item["question"] == followup_question for item in history["history"])
