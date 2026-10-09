import pandas as pd

from frontend.components.charts import build_figure


def test_recommended_bar_chart_builds_plotly_figure():
    frame = pd.DataFrame([{"customer": "A", "revenue": 125.0}, {"customer": "B", "revenue": 90.0}])
    figure = build_figure(
        frame,
        {"type": "bar", "x": "customer", "y": "revenue"},
        "bar",
        "Customer revenue",
    )
    assert figure is not None
    assert figure.layout.title.text == "Customer revenue"
    assert len(figure.data) == 1


def test_table_recommendation_returns_no_figure():
    frame = pd.DataFrame([{"value": "only text"}])
    assert build_figure(frame, {"type": "table"}, "table", "Results") is None
