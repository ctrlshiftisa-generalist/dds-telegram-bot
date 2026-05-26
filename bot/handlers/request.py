"""Request creation flow handler — full FSM-based flow with edit support."""

import asyncio
import logging
from typing import Set

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import database as db
from bot.keyboards import (
    main_menu_kb,
    operations_kb,
    projects_kb,
    confirm_kb,
    edit_field_kb,
)
from bot.states import RequestCreation
from bot.utils import parse_amount, format_amount, get_current_period, get_today_date, format_card_number
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)

router = Router()

# Double-click protection: set of user IDs currently submitting
_submitting_users: Set[int] = set()
_submit_lock = asyncio.Lock()


def _build_confirmation_text(data: dict) -> str:
    """Build the confirmation message text."""
    return (
        "📋 <b>Проверьте заявку:</b>\n\n"
        f"📅 Дата: {data['date']}\n"
        f"📂 Тип операции: {data['operation_type']}\n"
        f"💰 Сумма: {format_amount(data['amount'])}\n"
        f"🏢 Проект: {data['project']}\n"
        f"💳 Реквизиты: {data['card']}\n"
        f"📝 Назначение: {data['purpose']}"
    )


async def _go_to_confirmation(message_or_callback, state: FSMContext):
    """Show confirmation screen. Works with both Message and CallbackQuery."""
    data = await state.get_data()
    # Update date and period on each confirmation
    data["date"] = get_today_date()
    data["period"] = get_current_period()
    await state.update_data(date=data["date"], period=data["period"])
    await state.set_state(RequestCreation.confirming)

    text = _build_confirmation_text(data)
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=confirm_kb()
        )
    else:
        await message_or_callback.answer(
            text, parse_mode="HTML", reply_markup=confirm_kb()
        )


def _is_editing(data: dict) -> bool:
    """Check if all required fields are already filled (i.e. we're in edit mode)."""
    required = ["operation_type", "amount", "project", "card", "purpose"]
    return all(k in data for k in required)


# ── Step 1: Start request / Choose operation type ──────────────────────────

@router.message(F.text == "📝 Создать заявку")
async def start_request(message: Message, state: FSMContext, sheets: SheetsService):
    """Begin the request creation flow."""
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("⚠️ Вы уже создаете заявку. Завершите её или нажмите /cancel для отмены.")
        return

    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Нажмите /start")
        return

    # Check if user's name is still in the active list of users from Google Sheets
    users = await asyncio.to_thread(sheets.get_users)
    if user["name"] not in users:
        await message.answer(
            f"⚠️ Вашего имени (<b>{user['name']}</b>) больше нет в списке сотрудников в Google Таблице.\n\n"
            "Пожалуйста, обновите ваш профиль с помощью команды /start или обратитесь к администратору.",
            parse_mode="HTML"
        )
        return

    await state.clear()
    await state.update_data(employee_name=user["name"])
    await state.set_state(RequestCreation.choosing_operation)
    await message.answer("Выберите тип операции:", reply_markup=operations_kb())



@router.callback_query(RequestCreation.choosing_operation, F.data.startswith("op:"))
async def operation_chosen(callback: CallbackQuery, state: FSMContext):
    operation = callback.data.split(":", 1)[1]
    await state.update_data(operation_type=operation)
    data = await state.get_data()

    if _is_editing(data):
        await _go_to_confirmation(callback, state)
    else:
        await state.set_state(RequestCreation.entering_amount)
        await callback.message.edit_text(
            f"Тип операции: <b>{operation}</b>\n\n💰 Введите сумму:",
            parse_mode="HTML",
        )
    await callback.answer()


# ── Step 2: Enter amount ───────────────────────────────────────────────────

@router.message(RequestCreation.entering_amount)
async def amount_entered(message: Message, state: FSMContext, sheets: SheetsService):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(
            "❌ Некорректная сумма. Введите число, например:\n"
            "<code>9000</code>, <code>9 000</code>, <code>9 245.5</code>",
            parse_mode="HTML",
        )
        return

    await state.update_data(amount=amount)
    data = await state.get_data()

    if _is_editing(data):
        await _go_to_confirmation(message, state)
    else:
        await state.set_state(RequestCreation.choosing_project)
        projects = await asyncio.to_thread(sheets.get_projects)
        if not projects:
            await message.answer("⚠️ Список проектов пуст. Обратитесь к администратору.")
            return

        await message.answer(
            f"Сумма: <b>{format_amount(amount)}</b>\n\n🏢 Выберите проект:",
            parse_mode="HTML",
            reply_markup=projects_kb(projects),
        )


# ── Step 3: Choose project ────────────────────────────────────────────────


@router.callback_query(RequestCreation.choosing_project, F.data.startswith("proj:"))
async def project_chosen(callback: CallbackQuery, state: FSMContext):
    project = callback.data.split(":", 1)[1]
    await state.update_data(project=project)
    data = await state.get_data()

    if _is_editing(data):
        await _go_to_confirmation(callback, state)
    else:
        await state.set_state(RequestCreation.entering_card)
        await callback.message.edit_text(
            f"Проект: <b>{project}</b>\n\n💳 Введите реквизиты карты:",
            parse_mode="HTML",
        )
    await callback.answer()


# ── Step 4: Enter card ───────────────────────────────────────────────────

@router.message(RequestCreation.entering_card)
async def card_entered(message: Message, state: FSMContext):
    card = message.text.strip()
    if not card:
        await message.answer("❌ Реквизиты не могут быть пустыми. Введите текст:")
        return

    cleaned = card.replace(" ", "").replace("-", "").strip()
    if not cleaned.isdigit() or len(cleaned) != 16:
        await message.answer("❌ Некорректные реквизиты. Введите 16 цифр номера карты:")
        return

    card = format_card_number(card)
    await state.update_data(card=card)
    data = await state.get_data()

    if _is_editing(data):
        await _go_to_confirmation(message, state)
    else:
        await state.set_state(RequestCreation.entering_purpose)
        await message.answer(
            f"Реквизиты: <b>{card}</b>\n\n📝 Введите кому и на что эти деньги тратятся:",
            parse_mode="HTML"
        )


# ── Step 5: Enter purpose ────────────────────────────────────────────────

@router.message(RequestCreation.entering_purpose)
async def purpose_entered(message: Message, state: FSMContext):
    purpose = message.text.strip()
    if not purpose:
        await message.answer("❌ Назначение не может быть пустым. Введите текст:")
        return

    await state.update_data(purpose=purpose)
    await _go_to_confirmation(message, state)


# ── Step 5: Confirmation ──────────────────────────────────────────────────

@router.callback_query(RequestCreation.confirming, F.data == "confirm_submit")
async def confirm_submit(callback: CallbackQuery, state: FSMContext, sheets: SheetsService):
    user_id = callback.from_user.id

    # Double-click protection
    async with _submit_lock:
        if user_id in _submitting_users:
            await callback.answer("⏳ Заявка уже отправляется...", show_alert=True)
            return
        _submitting_users.add(user_id)

    try:
        data = await state.get_data()

        # Check users and projects first
        users = await asyncio.to_thread(sheets.get_users)
        projects = await asyncio.to_thread(sheets.get_projects)

        is_user_valid = data["employee_name"] in users
        is_project_valid = data["project"] in projects

        if not is_user_valid or not is_project_valid:
            error_details = []
            if not is_user_valid:
                error_details.append(f"пользователь '<b>{data['employee_name']}</b>' отсутствует в списке сотрудников")
                logger.warning("Submission failed: user %s not in %s", data["employee_name"], users)
            if not is_project_valid:
                error_details.append(f"проект '<b>{data['project']}</b>' отсутствует в списке проектов")
                logger.warning("Submission failed: project %s not in %s", data["project"], projects)
            
            error_msg = (
                "❌ <b>Ошибка валидации данных:</b>\n\n"
                + "\n".join(f"— {detail}" for detail in error_details) +
                "\n\nПожалуйста, обновите ваш профиль (/start) или выберите корректные значения."
            )
            await callback.message.edit_text(error_msg, parse_mode="HTML")
            await callback.message.answer(
                "Выберите действие:", reply_markup=main_menu_kb()
            )
            await state.clear()
            return


        # Immediately remove buttons to prevent re-clicks
        await callback.message.edit_text(
            _build_confirmation_text(data) + "\n\n⏳ <i>Отправка в таблицу...</i>",
            parse_mode="HTML",
        )

        result = await asyncio.to_thread(
            lambda: sheets.append_row(
                date=data["date"],
                operation_type=data["operation_type"],
                amount=data["amount"],
                employee_name=data["employee_name"],
                project=data["project"],
                period=data["period"],
                comment=f"{data['card']}\n{data['purpose']}",
            )
        )

        if result is not None:
            updated_range = result.get("updates", {}).get("updatedRange", "неизвестно")
            await db.save_request(
                telegram_id=user_id,
                employee_name=data["employee_name"],
                date=data["date"],
                operation_type=data["operation_type"],
                amount=data["amount"],
                project=data["project"],
                period=data["period"],
                comment=f"{data['card']}\n{data['purpose']}",
                status="sent",
            )
            await callback.message.edit_text(
                f"✅ <b>Заявка успешно добавлена в таблицу!</b>\n"
                f"Диапазон: {updated_range}\n\n"
                + _build_confirmation_text(data),
                parse_mode="HTML",
            )
            await callback.message.answer(
                "Выберите действие:", reply_markup=main_menu_kb()
            )
        else:
            await db.save_request(
                telegram_id=user_id,
                employee_name=data["employee_name"],
                date=data["date"],
                operation_type=data["operation_type"],
                amount=data["amount"],
                project=data["project"],
                period=data["period"],
                comment=f"{data['card']}\n{data['purpose']}",
                status="error",
            )
            await callback.message.edit_text(
                "❌ Не удалось добавить заявку в таблицу. "
                "Попробуйте позже или обратитесь к администратору.",
            )
            await callback.message.answer(
                "Выберите действие:", reply_markup=main_menu_kb()
            )

        await state.clear()

    finally:
        async with _submit_lock:
            _submitting_users.discard(user_id)

    await callback.answer()


# ── Edit flow ──────────────────────────────────────────────────────────────

@router.callback_query(RequestCreation.confirming, F.data == "edit_request")
async def edit_request(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RequestCreation.editing_field)
    await callback.message.edit_text(
        "✏️ Что хотите изменить?", reply_markup=edit_field_kb()
    )
    await callback.answer()


@router.callback_query(RequestCreation.editing_field, F.data == "back_to_confirm")
async def back_to_confirm(callback: CallbackQuery, state: FSMContext):
    await _go_to_confirmation(callback, state)
    await callback.answer()


@router.callback_query(RequestCreation.editing_field, F.data.startswith("edit_field:"))
async def edit_field_chosen(callback: CallbackQuery, state: FSMContext, sheets: SheetsService):
    field = callback.data.split(":", 1)[1]

    if field == "operation":
        await state.set_state(RequestCreation.choosing_operation)
        await callback.message.edit_text(
            "Выберите новый тип операции:", reply_markup=operations_kb()
        )
    elif field == "amount":
        await state.set_state(RequestCreation.entering_amount)
        await callback.message.edit_text("💰 Введите новую сумму:")
    elif field == "project":
        projects = await asyncio.to_thread(sheets.get_projects)
        if not projects:
            await callback.answer("⚠️ Список проектов пуст.", show_alert=True)
            return
        await state.set_state(RequestCreation.choosing_project)
        await callback.message.edit_text(
            "🏢 Выберите проект:", reply_markup=projects_kb(projects)
        )
    elif field == "card":
        await state.set_state(RequestCreation.entering_card)
        await callback.message.edit_text("💳 Введите новые реквизиты карты:")
    elif field == "purpose":
        await state.set_state(RequestCreation.entering_purpose)
        await callback.message.edit_text("📝 Введите новое назначение платежа:")

    await callback.answer()


# ── Cancel request ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_request")
async def cancel_request(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Заявка отменена.")
    await callback.message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await callback.answer()
