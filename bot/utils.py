"""Utility functions for number formatting and period generation."""

import re
from datetime import datetime
from typing import Optional

# Russian month abbreviations for the period field
MONTH_ABBR = {
    1: "янв.",
    2: "фев.",
    3: "мар.",
    4: "апр.",
    5: "май.",
    6: "июн.",
    7: "июл.",
    8: "авг.",
    9: "сен.",
    10: "окт.",
    11: "ноя.",
    12: "дек.",
}


def parse_amount(text: str) -> Optional[float]:
    """
    Parse user-entered amount string to a float.
    Handles formats: 9000, 9 000, 900000, 900 000, 9 245.5, 9 245,5
    Returns None if the text is not a valid number.
    """
    cleaned = text.strip()
    # Remove spaces (thousands separator)
    cleaned = cleaned.replace(" ", "").replace("\u00a0", "")
    # Replace comma with dot for decimal
    cleaned = cleaned.replace(",", ".")

    # Validate: should be a positive number
    if not re.match(r"^\d+(\.\d+)?$", cleaned):
        return None

    try:
        value = float(cleaned)
        if value <= 0:
            return None
        return value
    except ValueError:
        return None


def format_amount(amount: float) -> str:
    """Format number with space as thousands separator for display."""
    if amount == int(amount):
        # Integer display: 9 000
        return f"{int(amount):,}".replace(",", " ")
    else:
        # Float display: 9 245.50
        integer_part = int(amount)
        decimal_part = amount - integer_part
        formatted_int = f"{integer_part:,}".replace(",", " ")
        decimal_str = f"{decimal_part:.2f}"[1:]  # ".50"
        return f"{formatted_int}{decimal_str}"


def get_current_period() -> str:
    """Get current period string in format 'май. 26'."""
    now = datetime.now()
    month_str = MONTH_ABBR[now.month]
    year_str = str(now.year)[-2:]  # Last 2 digits
    return f"{month_str} {year_str}"


def get_today_date() -> str:
    """Get today's date in dd.mm.yyyy format."""
    return datetime.now().strftime("%d.%m.%Y")


def format_card_number(text: str) -> str:
    """Format PAN with spaces if it's 16 digits."""
    cleaned = text.replace(" ", "").strip()
    if cleaned.isdigit() and len(cleaned) == 16:
        return f"{cleaned[:4]} {cleaned[4:8]} {cleaned[8:12]} {cleaned[12:]}"
    return text
