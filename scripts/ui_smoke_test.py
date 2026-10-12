"""Exercise every Streamlit page against a running local QueryMind API."""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PAGES = [
    "Overview",
    "Ask Your Data",
    "Database Connections",
    "Query History",
    "Saved Queries",
    "AI Settings",
    "About",
]


def assert_healthy(app: AppTest, page: str) -> None:
    if app.exception:
        messages = "; ".join(str(item.value) for item in app.exception)
        raise AssertionError(f"{page} raised a Streamlit exception: {messages}")
    if any("API offline" in str(item.value) for item in app.error):
        raise AssertionError(f"{page} could not reach the local API")


def main() -> None:
    app = AppTest.from_file(str(ROOT / "frontend" / "app.py"), default_timeout=20)
    app.run()
    assert_healthy(app, "Overview")
    print("Overview: ok")
    for page in PAGES[1:]:
        app.radio[0].set_value(page)
        app.run()
        assert_healthy(app, page)
        print(f"{page}: ok")
    app.radio[0].set_value("Ask Your Data")
    app.run()
    example = next(
        button for button in app.button if button.label == "Show the top 10 products by revenue."
    )
    example.click()
    app.run()
    assert_healthy(app, "Ask Your Data example validation")
    run_query = next(button for button in app.button if button.label == "Run Query")
    run_query.click()
    app.run()
    assert_healthy(app, "Ask Your Data example execution")
    if not app.dataframe:
        raise AssertionError("Example execution did not render a results table")
    print("Ask Your Data demo validation/execution: ok")
    next(button for button in app.button if button.label == "New analysis").click()
    app.run()
    assert_healthy(app, "Ask Your Data new-analysis reset")
    if app.session_state["question"] or app.text_area[0].value:
        raise AssertionError("New analysis did not clear the question widget")
    if app.session_state["conversation"]:
        raise AssertionError("New analysis did not clear conversation context")
    for key in ("generation", "validation", "result", "insight", "execution_error"):
        if app.session_state[key] is not None:
            raise AssertionError(f"New analysis did not clear {key}")
    print("Ask Your Data new-analysis callback reset: ok")
    app.radio[0].set_value("AI Settings")
    app.run()
    provider_select = next(item for item in app.selectbox if item.label == "Provider")
    api_key_input = next(item for item in app.text_input if item.label == "API key")
    model_input = next(item for item in app.text_input if item.label == "Model identifier")
    api_key_input.set_value("gemini-session-test-key")
    model_input.set_value("gemini-session-test-model")
    app.run()
    provider_select = next(item for item in app.selectbox if item.label == "Provider")
    provider_select.select("groq")
    app.run()
    groq_key = next(item for item in app.text_input if item.label == "API key")
    if groq_key.value:
        raise AssertionError("Provider switching leaked the prior provider's API key widget")
    profiles = app.session_state["provider_profiles"]
    if profiles["gemini"]["api_key"] != "gemini-session-test-key":
        raise AssertionError("Gemini settings were not preserved after switching providers")
    if profiles["groq"]["api_key"]:
        raise AssertionError("Groq profile inherited the Gemini API key")
    print("AI Settings provider isolation/switching: ok")


if __name__ == "__main__":
    main()
