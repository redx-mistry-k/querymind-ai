from frontend.components.state import RESET_ANALYSIS_KEYS, reset_analysis_state


def test_reset_analysis_state_preserves_settings_and_clears_analysis():
    state = {
        "question": "Show monthly revenue",
        "conversation": [{"role": "user", "content": "Old question"}],
        "generation": {"sql": "SELECT 1"},
        "validation": {"valid": True},
        "result": {"rows": [{"value": 1}]},
        "insight": "Old insight",
        "execution_error": "Old error",
        "provider": "gemini",
        "active_database": "demo",
    }

    reset_analysis_state(state)

    assert state["question"] == ""
    assert state["conversation"] == []
    assert all(state[key] is None for key in RESET_ANALYSIS_KEYS)
    assert state["provider"] == "gemini"
    assert state["active_database"] == "demo"
