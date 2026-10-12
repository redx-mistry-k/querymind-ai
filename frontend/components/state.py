from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

RESET_ANALYSIS_KEYS = ("generation", "validation", "result", "insight", "execution_error")


def reset_analysis_state(state: MutableMapping[str, Any]) -> None:
    for key in RESET_ANALYSIS_KEYS:
        state[key] = None
    state["question"] = ""
    state["conversation"] = []
