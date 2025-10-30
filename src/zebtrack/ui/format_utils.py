"""
UI formatting utilities.

Shared formatting functions used across UI components.
"""

import re


def format_day_display(value):
    """
    Format day value for display.

    Args:
        value: Day value (int, float, str, or None)

    Returns:
        str: Formatted day string (e.g., "01", "02", "Sem Dia", or "")
    """
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return f"{int(value):02d}"
        except (TypeError, ValueError):
            return str(value)
    value_str = str(value).strip()
    if not value_str:
        return ""
    lower_value = value_str.lower()
    if lower_value == "sem dia":
        return "Sem Dia"
    match = re.search(r"(\d+)", value_str)
    if match:
        try:
            return f"{int(match.group(1)):02d}"
        except ValueError:
            return value_str
    return value_str
