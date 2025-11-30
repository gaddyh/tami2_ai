# state.py
from __future__ import annotations

from typing import TypedDict, Any, Dict, List, Optional


class ConfirmationState(TypedDict, total=False):
    """
    Generic confirmation / disambiguation flow.

    For recipients use-case:
    - query: raw name/text to confirm ("גל", "גל ליס", product name, etc.)
    - options: list of candidate options to choose from
    - user_answer: user's reply after we asked a clarification question

    LLM outputs:
    - initial_result: first LLM call (decide vs ask question)
    - final_result: second LLM call (after user_answer)

    Final:
    - selected_item: chosen option (or None)
    """
    query: Optional[str]
    options: List[Dict[str, Any]]
    user_answer: Optional[str]

    initial_result: Optional[Dict[str, Any]]
    final_result: Optional[Dict[str, Any]]

    selected_item: Optional[Dict[str, Any]]

    llm_messages: Optional[List[Dict[str, Any]]]