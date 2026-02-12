"""Token-based template filling for EddyPro config files."""

from __future__ import annotations

from typing import Mapping


def fill_tokens(template_text: str, replacements: Mapping[str, str]) -> str:
    """Replace ``{{TOKEN}}`` placeholders and fail if any remain."""
    output = template_text
    for token, value in replacements.items():
        output = output.replace(f"{{{{{token}}}}}", value)

    tokens = _find_unreplaced_tokens(output)
    if tokens:
        raise ValueError(f"Unreplaced tokens found in template: {', '.join(tokens)}")

    if not output.endswith("\n"):
        output += "\n"
    return output


def _find_unreplaced_tokens(text: str) -> list[str]:
    """Return all unique ``{{TOKEN}}`` placeholders remaining in the filled text."""
    tokens: list[str] = []
    cursor = 0
    while True:
        start = text.find("{{", cursor)
        if start == -1:
            break
        end = text.find("}}", start + 2)
        if end == -1:
            break
        token = text[start : end + 2]
        if token not in tokens:
            tokens.append(token)
        cursor = end + 2
    return tokens
