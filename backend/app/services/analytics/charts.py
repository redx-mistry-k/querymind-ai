from __future__ import annotations

from typing import Any

import pandas as pd


def recommend_chart(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"type": "table", "reason": "No rows were returned."}
    frame = pd.DataFrame(rows)
    if frame.shape == (1, 1) and pd.api.types.is_numeric_dtype(frame.iloc[:, 0]):
        return {"type": "kpi", "value_column": frame.columns[0], "reason": "Single numeric result."}
    numeric = list(frame.select_dtypes(include="number").columns)
    non_numeric = [column for column in frame.columns if column not in numeric]
    date_columns = []
    for column in non_numeric:
        name = str(column).lower()
        if any(token in name for token in ("date", "month", "year", "time")):
            parsed = pd.to_datetime(frame[column], errors="coerce")
            if parsed.notna().mean() > 0.7:
                date_columns.append(column)
    if date_columns and numeric:
        return {
            "type": "line",
            "x": date_columns[0],
            "y": numeric[0],
            "reason": "Time and numeric columns.",
        }
    if non_numeric and numeric:
        chart_type = "horizontal_bar" if len(frame) > 8 else "bar"
        return {
            "type": chart_type,
            "x": non_numeric[0],
            "y": numeric[0],
            "reason": "Category and numeric columns.",
        }
    if len(numeric) >= 2:
        return {
            "type": "scatter",
            "x": numeric[0],
            "y": numeric[1],
            "reason": "Two numeric measures.",
        }
    if len(numeric) == 1:
        return {"type": "histogram", "x": numeric[0], "reason": "Numeric distribution."}
    return {"type": "table", "reason": "Tabular data is the clearest representation."}


def deterministic_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "The query completed successfully but returned no rows."
    frame = pd.DataFrame(rows)
    numeric = frame.select_dtypes(include="number")
    parts = [f"The query returned {len(frame):,} row{'s' if len(frame) != 1 else ''}."]
    categorical = [column for column in frame.columns if column not in numeric.columns]
    if len(frame) == 1 and len(numeric.columns) == 1:
        column = numeric.columns[0]
        value = numeric.iloc[0][column]
        return f"{column} is {value:,.2f}."
    if categorical and len(numeric.columns):
        measure = numeric.columns[0]
        values = numeric[measure].dropna()
        if not values.empty:
            top_index = values.idxmax()
            label = frame.loc[top_index, categorical[0]]
            top_value = values.loc[top_index]
            total = values.sum()
            share = (
                f", representing {top_value / total:.1%} of the displayed total"
                if total > 0
                else ""
            )
            parts.append(f"The leading {categorical[0]} is {label} at {top_value:,.2f}{share}.")
    date_column = next(
        (
            column
            for column in frame.columns
            if any(token in str(column).lower() for token in ("date", "month", "year", "time"))
        ),
        None,
    )
    if date_column and len(numeric.columns) and len(frame) > 1:
        ordered = frame.assign(
            _querymind_date=pd.to_datetime(frame[date_column], errors="coerce")
        ).dropna(subset=["_querymind_date"])
        ordered = ordered.sort_values("_querymind_date")
        if len(ordered) > 1:
            measure = numeric.columns[0]
            first, last = ordered.iloc[0][measure], ordered.iloc[-1][measure]
            if pd.notna(first) and pd.notna(last) and first != 0:
                parts.append(
                    f"From the first to last displayed period, {measure} changed by {(last - first) / abs(first):.1%}."
                )
    for column in numeric.columns[:3]:
        series = numeric[column].dropna()
        if not series.empty:
            parts.append(
                f"{column}: total {series.sum():,.2f}, average {series.mean():,.2f}, "
                f"range {series.min():,.2f}–{series.max():,.2f}."
            )
    return " ".join(parts)


def suggest_followups(question: str, rows: list[dict[str, Any]]) -> list[str]:
    columns = {str(column).lower() for row in rows[:1] for column in row}
    suggestions: list[str] = []
    if not any(token in question.lower() for token in ("month", "date", "year", "trend")):
        suggestions.append("Break this result down by month.")
    if any(token in " ".join(columns) for token in ("revenue", "sales", "amount", "total")):
        suggestions.append("Compare this result with the previous year.")
    suggestions.append("Which segment contributed the most, and by how much?")
    return suggestions[:3]
