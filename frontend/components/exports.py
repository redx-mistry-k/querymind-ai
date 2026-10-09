from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd


def rows_to_csv(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    return pd.DataFrame(rows, columns=columns).to_csv(index=False).encode("utf-8")


def rows_to_xlsx(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    frame = pd.DataFrame(rows, columns=columns)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Query Results")
    return output.getvalue()
