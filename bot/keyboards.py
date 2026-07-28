"""All keyboard builders for the bot."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


# ── Main menu (reply keyboard) ────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать заявку")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
    )


# ── Operation types (inline, built dynamically from DB) ───────────────────

def operations_kb(operation_types: list[str]) -> InlineKeyboardMarkup:
    """
    Build operation type keyboard from Google Sheets list.
    """
    buttons = []
    row = []
    for op_name in operation_types:
        row.append(InlineKeyboardButton(text=op_name, callback_data=f"op:{op_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_request")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Projects (inline, 2-column grid) ─────────────────────────────────────

def projects_kb(projects: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for p in projects:
        row.append(InlineKeyboardButton(text=p, callback_data=f"proj:{p}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_request")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Users (inline, one per row) ──────────────────────────────────────────

def users_kb(users: list[str]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=u, callback_data=f"user:{u}")] for u in users]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def positions_kb(positions: list[str]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=p, callback_data=f"pos:{p}")] for p in positions]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Confirmation ──────────────────────────────────────────────────────────

def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Добавить в таблицу", callback_data="confirm_submit")],
        [
            InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_request"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_request"),
        ],
    ])


# ── Edit field selector ───────────────────────────────────────────────────

def edit_field_kb(has_project_choice: bool = True) -> InlineKeyboardMarkup:
    """
    has_project_choice=False when project was assigned automatically
    (Подписки / Другое) — no project button shown.
    """
    rows = [
        [InlineKeyboardButton(text="Тип операции", callback_data="edit_field:operation")],
        [InlineKeyboardButton(text="Сумма", callback_data="edit_field:amount")],
    ]
    if has_project_choice:
        rows.append([InlineKeyboardButton(text="Проект", callback_data="edit_field:project")])
    rows.append([InlineKeyboardButton(text="Реквизиты / Назначение", callback_data="edit_field:requisites")])
    rows.append([InlineKeyboardButton(text="← Назад к подтверждению", callback_data="back_to_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Отмена", callback_data="admin_cancel")],
    ])

def users_access_kb(users: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard for managing user access."""
    buttons = []
    for user in users:
        status_icon = "🚫" if user.get("is_banned") else "✅"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_icon} {user['name']}",
                callback_data=f"toggle_ban:{user['telegram_id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="Закрыть", callback_data="admin_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
