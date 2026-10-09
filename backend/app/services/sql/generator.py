from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from backend.app.schemas.api import StructuredSQL
from backend.app.services.llm.base import LLMError, LLMProvider

SYSTEM_PROMPT = """You generate one read-only SQL query for an analytics application.
Return JSON only with keys: sql, explanation, referenced_tables, assumptions,
clarification_needed, suggested_chart. Never use DDL/DML, SELECT INTO, system tables,
or columns absent from the supplied schema. Use only the supplied dialect and schema.
If ambiguous or impossible, set sql to an empty string and explain in clarification_needed.
Do not claim that the query executed. suggested_chart must be one of bar, horizontal_bar,
line, area, scatter, pie, histogram, table, kpi."""


@dataclass
class CorrectionBudget:
    max_attempts: int = 2
    attempts: dict[str, int] = field(default_factory=dict)

    def start(self) -> str:
        analysis_id = uuid4().hex
        self.attempts[analysis_id] = 0
        return analysis_id

    def consume(self, analysis_id: str) -> bool:
        count = self.attempts.get(analysis_id)
        if count is None or count >= self.max_attempts:
            return False
        self.attempts[analysis_id] = count + 1
        return True


def select_relevant_schema(
    question: str, schema: dict[str, Any], maximum: int = 8
) -> list[dict[str, Any]]:
    words = set(re.findall(r"[a-z0-9_]+", question.lower()))
    scored: list[tuple[int, dict[str, Any]]] = []
    foreign_targets: set[str] = set()
    for table in schema["tables"]:
        haystack = {table["name"].lower()}
        haystack.update(column["name"].lower() for column in table["columns"])
        score = sum(3 if word == table["name"].lower() else 1 for word in words if word in haystack)
        # Basic singular/plural matching helps concise prompts without embeddings.
        if table["name"].lower().rstrip("s") in {word.rstrip("s") for word in words}:
            score += 3
        scored.append((score, table))
    selected = [
        table
        for score, table in sorted(scored, key=lambda item: item[0], reverse=True)
        if score > 0
    ][:maximum]
    if not selected:
        selected = [table for _, table in scored[:maximum]]
    names = {item["name"] for item in selected}
    while len(selected) < maximum:
        foreign_targets.clear()
        for table in schema["tables"]:
            table_name = table["name"]
            for fk in table["foreign_keys"]:
                referred = fk.get("referred_table")
                if table_name in names and referred:
                    foreign_targets.add(referred)
                if referred in names:
                    foreign_targets.add(table_name)
        additions = [
            table
            for table in schema["tables"]
            if table["name"] in foreign_targets and table["name"] not in names
        ][: maximum - len(selected)]
        if not additions:
            break
        selected.extend(additions)
        names.update(table["name"] for table in additions)
    return selected


def compact_schema(tables: list[dict[str, Any]]) -> str:
    lines = []
    for table in tables:
        columns = ", ".join(
            f"{column['name']} {column['type']}{' PK' if column['primary_key'] else ''}"
            for column in table["columns"]
        )
        lines.append(f"{table['name']}({columns})")
        for fk in table["foreign_keys"]:
            lines.append(
                f"FK {table['name']}.{','.join(fk['columns'])} -> "
                f"{fk['referred_table']}.{','.join(fk['referred_columns'])}"
            )
    return "\n".join(lines)


def _json_payload(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise LLMError("The model did not return structured JSON.", "invalid_response")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("The model returned malformed JSON.", "invalid_response") from exc


async def generate_sql(
    provider: LLMProvider,
    question: str,
    schema: dict[str, Any],
    conversation: list[dict[str, str]],
    max_turns: int,
) -> tuple[StructuredSQL, dict[str, Any] | None]:
    relevant = select_relevant_schema(question, schema)
    rules = schema.get("business_rules") or []
    rule_lines = "\n- ".join(rules)
    rule_context = f"\nBusiness rules:\n- {rule_lines}" if rules else ""
    user_prompt = (
        f"Dialect: {schema['dialect']}\nSchema:\n{compact_schema(relevant)}"
        f"{rule_context}\nQuestion: {question}"
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation[-max_turns:])
    messages.append({"role": "user", "content": user_prompt})
    response = await provider.complete(messages)
    try:
        structured = StructuredSQL.model_validate(_json_payload(response.text))
    except ValidationError as exc:
        raise LLMError(
            "The model response did not match the required SQL format.", "invalid_response"
        ) from exc
    return structured, response.usage


async def correct_sql(
    provider: LLMProvider,
    question: str,
    sql: str,
    safe_error: str,
    schema: dict[str, Any],
) -> StructuredSQL:
    rules = schema.get("business_rules") or []
    rule_lines = "\n- ".join(rules)
    rule_context = f"\nBusiness rules:\n- {rule_lines}" if rules else ""
    prompt = (
        f"Dialect: {schema['dialect']}\nSchema:\n{compact_schema(select_relevant_schema(question, schema))}"
        f"{rule_context}"
        f"\nQuestion: {question}\nFailed SQL: {sql}\nDatabase error: {safe_error}\nCorrect the SQL."
    )
    response = await provider.complete(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    )
    try:
        return StructuredSQL.model_validate(_json_payload(response.text))
    except ValidationError as exc:
        raise LLMError(
            "The corrected response was not valid structured SQL.", "invalid_response"
        ) from exc
