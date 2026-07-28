"""Utility functions for number formatting and period generation."""

import re
from datetime import datetime
from typing import Optional

# Russian month names for the period field
MONTH_ABBR = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
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
    """Get current period string in format '01.mm.yyyy'."""
    now = datetime.now()
    return f"01.{now.strftime('%m.%Y')}"


def get_today_date() -> str:
    """Get today's date in dd.mm.yyyy format."""
    return datetime.now().strftime("%d.%m.%Y")


def format_card_number(text: str) -> str:
    """Format PAN with spaces if it's 16 digits."""
    cleaned = text.replace(" ", "").strip()
    if cleaned.isdigit() and len(cleaned) == 16:
        return f"{cleaned[:4]} {cleaned[4:8]} {cleaned[8:12]} {cleaned[12:]}"
    return text


def parse_card_input(text: str) -> tuple[bool, str, str]:
    """
    Parse and validate requisites input.
    
    Expected format: 16 digits (MUST be formatted with spaces: 0000 0000 0000 0000) 
    + optional comment after space.
    
    Returns:
        (is_valid, formatted_text, error_message)
    """
    raw = text.strip()
    if not raw:
        return False, "", "❌ Реквизиты не могут быть пустыми."
    
    # Check if the text starts with 16 digits formatted properly with spaces
    match = re.match(r"^(\d{4} \d{4} \d{4} \d{4})(?:\s+(.*))?$", raw)
    if match:
        card_str = match.group(1)
        comment = match.group(2)
        if comment:
            return True, f"{card_str} {comment.strip()}", ""
        else:
            return True, card_str, ""
            
    # If it didn't match the exact format, let's see if they at least provided 16 digits
    digits_only = re.sub(r"\D", "", raw)
    if len(digits_only) >= 16:
        # They provided 16 digits but without proper spaces
        return False, "", "❌ Пожалуйста, добавьте пробелы между каждыми 4 цифрами номера карты (формат: 0000 0000 0000 0000)."
        
    return False, "", (
        "❌ Введите корректные реквизиты.\n\n"
        "Формат: <b>16 цифр номера карты (обязательно с пробелами)</b> + назначение платежа\n"
        "Например: <code>1234 5678 9012 3456 за аренду студии</code>"
    )

