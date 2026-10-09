from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure


def build_figure(
    frame: pd.DataFrame,
    recommendation: dict[str, Any],
    selected: str,
    title: str,
) -> Figure | None:
    numeric = list(frame.select_dtypes(include="number").columns)
    categorical = [item for item in frame.columns if item not in numeric]
    x = recommendation.get("x") or (
        categorical[0] if categorical else (numeric[0] if numeric else None)
    )
    y = recommendation.get("y") or (numeric[0] if numeric else None)
    if selected == "bar" and x and y:
        return px.bar(frame, x=x, y=y, title=title)
    if selected == "horizontal_bar" and x and y:
        return px.bar(frame, x=y, y=x, orientation="h", title=title)
    if selected in {"line", "area"} and x and y:
        function = px.line if selected == "line" else px.area
        return function(frame, x=x, y=y, markers=True, title=title)
    if selected == "scatter" and len(numeric) >= 2:
        return px.scatter(frame, x=numeric[0], y=numeric[1], title=title)
    if selected == "pie" and categorical and numeric:
        return px.pie(frame, names=categorical[0], values=numeric[0], title=title)
    if selected == "histogram" and numeric:
        return px.histogram(frame, x=numeric[0], title=title)
    return None
