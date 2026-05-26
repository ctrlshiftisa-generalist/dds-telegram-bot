"""All keyboard builders for the bot."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# ── Constants ──────────────────────────────────────────────────────────────

OPERATION_TYPES = [
    "Съемки", "Пиар", "Подписки", "Другое"
]



# ── Main menu (reply keyboard) ────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать заявку")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
    )


# ── Operation types (inline) ──────────────────────────────────────────────

def operations_kb() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for op in OPERATION_TYPES:
        row.append(InlineKeyboardButton(text=op, callback_data=f"op:{op}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_request")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _project_list_kb(projects: list[str]) -> list[list[InlineKeyboardButton]]:
    """Build a 2-column grid of project buttons."""
    buttons = []
    row = []
    for p in projects:
        row.append(InlineKeyboardButton(text=p, callback_data=f"proj:{p}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


def projects_kb(projects: list[str]) -> InlineKeyboardMarkup:
    buttons = _project_list_kb(projects)
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_request")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def users_kb(users: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for u in users:
        buttons.append([InlineKeyboardButton(text=u, callback_data=f"user:{u}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Confirmation ───────────────────────────────────────────────────────────

def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Добавить в таблицу", callback_data="confirm_submit")],
        [
            InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_request"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_request"),
        ],
    ])


# ── Edit field selector ───────────────────────────────────────────────────

def edit_field_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Тип операции", callback_data="edit_field:operation"),
            InlineKeyboardButton(text="Сумма", callback_data="edit_field:amount"),
        ],
        [
            InlineKeyboardButton(text="Проект", callback_data="edit_field:project"),
        ],
        [
            InlineKeyboardButton(text="Реквизиты", callback_data="edit_field:card"),
            InlineKeyboardButton(text="Назначение", callback_data="edit_field:purpose"),
        ],
        [InlineKeyboardButton(text="← Назад к подтверждению", callback_data="back_to_confirm")],
    ])
