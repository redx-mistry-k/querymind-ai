import json

import pytest

from backend.app.services.llm.base import LLMProvider, LLMResponse
from backend.app.services.sql.generator import generate_sql, select_relevant_schema


class MockProvider(LLMProvider):
    async def complete(self, messages):
        return LLMResponse(
            text=json.dumps(
                {
                    "sql": "SELECT status, COUNT(*) AS orders FROM orders GROUP BY status",
                    "explanation": "Counts orders by status.",
                    "referenced_tables": ["orders"],
                    "assumptions": [],
                    "clarification_needed": None,
                    "suggested_chart": "bar",
                }
            ),
            usage={"input_tokens": 120, "output_tokens": 50},
        )


@pytest.mark.asyncio
async def test_structured_sql_generation_with_mock():
    schema = {
        "dialect": "sqlite",
        "tables": [
            {
                "name": "orders",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "status", "type": "TEXT", "primary_key": False},
                ],
                "foreign_keys": [],
            }
        ],
    }
    result, usage = await generate_sql(MockProvider("mock"), "Orders by status", schema, [], 6)
    assert result.referenced_tables == ["orders"]
    assert result.suggested_chart == "bar"
    assert usage["input_tokens"] == 120


def test_relevant_schema_selection():
    schema = {
        "tables": [
            {"name": "orders", "columns": [], "foreign_keys": []},
            {"name": "products", "columns": [], "foreign_keys": []},
        ]
    }
    selected = select_relevant_schema("top products", schema, maximum=1)
    assert selected[0]["name"] == "products"


def test_relevant_schema_expands_incoming_relationships_for_revenue_queries():
    schema = {
        "tables": [
            {"name": "categories", "columns": [], "foreign_keys": []},
            {
                "name": "products",
                "columns": [],
                "foreign_keys": [{"referred_table": "categories"}],
            },
            {
                "name": "order_items",
                "columns": [],
                "foreign_keys": [{"referred_table": "products"}, {"referred_table": "orders"}],
            },
            {"name": "orders", "columns": [], "foreign_keys": []},
        ]
    }
    selected = select_relevant_schema(
        "Which product category generates the highest revenue?", schema, maximum=4
    )
    assert {table["name"] for table in selected} == {
        "categories",
        "products",
        "order_items",
        "orders",
    }
