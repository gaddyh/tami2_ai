# agent/history.py
from typing import Any, Dict, Iterable, List


def _extract_text_content(content: Any) -> str:
    """
    Normalize various content shapes into a plain string.
    - str -> as is
    - list[dict] with parts (e.g. {"type": "text", "text": "..."}) -> join texts
    - dict -> try "text" or "content", else fallback to str()
    - anything else -> str()
    """
    if isinstance(content, str):
        return content

    # Multi-part content (OpenAI-style)
    if isinstance(content, list):
        parts: List[str] = []
        for p in content:
            if isinstance(p, dict):
                # Try common keys
                if "text" in p and isinstance(p["text"], str):
                    parts.append(p["text"])
                elif "content" in p and isinstance(p["content"], str):
                    parts.append(p["content"])
        if parts:
            return "\n".join(parts)
        return str(content)

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]
        return str(content)

    return str(content)


def convert_session_to_messages(
    items: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convert stored session items into OpenAI-style chat messages.

    We ONLY keep:
      - role: "user" | "assistant"
      - content: plain string

    We DROP:
      - tool messages
      - system messages
      - metadata, ids, etc.
    """
    messages: List[Dict[str, Any]] = []

    for item in items:
        role = item.get("role")
        if role not in ("user", "assistant"):
            # Skip tool/system/other roles if they ever get stored
            continue

        content = _extract_text_content(item.get("content", ""))
        if not content:
            continue

        messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    return messages
