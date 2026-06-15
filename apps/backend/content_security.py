from __future__ import annotations


DEFAULT_BLOCKLIST = (
    "spam",
    "hack",
)


def is_safe_text(content: str, blocklist: tuple[str, ...] = DEFAULT_BLOCKLIST) -> bool:
    lowered = content.lower()
    return not any(keyword in lowered for keyword in blocklist)
