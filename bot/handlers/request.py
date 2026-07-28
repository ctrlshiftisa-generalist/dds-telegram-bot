import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from ..states import RequestCreation
from ..keyboards import (
    main_menu_kb,
    operations_kb,
    projects_kb,
    confirm_kb,
    edit_field_kb,
)
from ..services.sheets import SheetsService
from ..config import settings
from .. import database as db
from ..utils import format_amount, format_card_number, parse_card_input, get_current_period, get_today_date

logger = logging.getLogger(__name__)
router = Router()

# In-memory lock for preventing double-clicks
_submit_lock = asyncio.Lock()
_submitting_users = set()


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_operations(telegram_id: int, sheets: SheetsService) -> list[str]:
    is_admin = (
        telegram_id in settings.developer_ids or 
        telegram_id == settings.owner_id or 
        await db.is_admin(telegram_id, settings.developer_ids, settings.owner_id)
    )
    if is_admin:
        return await asyncio.to_thread(sheets.get_all_operation_types)
    return await asyncio.to_thread(sheets.get_operation_types)

def _build_confirmation_text(data: dict) -> str:
    """Build the final confirmation message text."""
    amount_str = format_amount(data["amount"])
    
    # "Съёмки" -> show card format, otherwise generic requisites
    req_label = "Реквизиты/Назначение"
    
    text = (
        f"📋 <b>Проверьте данные заявки:</b>\n\n"
        f"📅 Дата: <b>{data['date']}</b>\n"
        f"👤 Заявитель: <b>{data['employee_name']}</b>\n"
        f"📊 Тип операции: <b>{data['operation_type']}</b>\n"
        f"🏢 Проект: <b>{data.get('project', 'A.M. Maison')}</b>\n"
        f"💰 Сумма: <b>{amount_str} сум</b>\n"
        f"💳 {req_label}:\n<code>{data['requisites']}</code>\n"
    )
    return text


async def _go_to_confirmation(message_or_callback, state: FSMContext):
    """Helper to transition to the confirmation step."""
    data = await state.get_data()
    text = _build_confirmation_text(data)
    
    kb = confirm_kb()

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(RequestCreation.confirming)


# ── Step 1: Choose Operation ──────────────────────────────────────────────

@router.message(F.text == "📝 Создать заявку", StateFilter("*"))
async def start_request(message: Message, state: FSMContext, sheets: SheetsService):
    # Prepare date/period
    now_date = get_today_date()
    period = get_current_period()

    # Get user name
    telegram_id = message.from_user.id
    user = await db.get_user(telegram_id)
    if not user:
        await message.answer("❌ Сначала зарегистрируйтесь (/start).")
        return
    employee_name = user["name"]

    await state.update_data(
        date=now_date,
        period=period,
        employee_name=employee_name,
    )
    
    operations = await _get_operations(telegram_id, sheets)
    if not operations:
        await message.answer("⚠️ Нет доступных типов операций.")
        return

    await state.set_state(RequestCreation.choosing_operation)
    await message.answer(
        "Выберите тип операции:", reply_markup=operations_kb(operations)
    )


@router.callback_query(RequestCreation.choosing_operation, F.data.startswith("op:"))
async def operation_chosen(callback: CallbackQuery, state: FSMContext, sheets: SheetsService):
    op_name = callback.data.split(":")[1]
    
    # We no longer validate against DB, trust the callback data from Sheets
    await state.update_data(
        operation_type=op_name,
        requisites_hint="Введите реквизиты и назначение платежа (например: 0000 0000 0000 0000 описание):",
    )

    # Fetch projects dynamically based on op_name
    projects = await asyncio.to_thread(
        sheets.get_projects_for_operation, 
        op_name
    )
    
    if projects:
        await state.set_state(RequestCreation.choosing_project)
        await callback.message.edit_text(
            "🏢 Выберите проект:", reply_markup=projects_kb(projects)
        )
    else:
        # Auto-assign default project if no project list exists for this operation
        await state.update_data(project="A.M. Maison")
        await state.set_state(RequestCreation.entering_amount)
        await callback.message.edit_text("💰 Введите сумму (только цифры):")

    await callback.answer()


# ── Step 2: Choose Project ────────────────────────────────────────────────

@router.callback_query(RequestCreation.choosing_project, F.data.startswith("proj:"))
async def project_chosen(callback: CallbackQuery, state: FSMContext):
    project = callback.data.split(":")[1]
    await state.update_data(project=project)

    await state.set_state(RequestCreation.entering_amount)
    await callback.message.edit_text("💰 Введите сумму (только цифры):")
    await callback.answer()


# ── Step 3: Enter Amount ──────────────────────────────────────────────────

@router.message(RequestCreation.entering_amount)
async def amount_entered(message: Message, state: FSMContext):
    raw_amount = message.text.replace(" ", "").replace(",", ".")
    try:
        amount = float(raw_amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Некорректная сумма. Пожалуйста, введите число (например, 50000):")
        return

    await state.update_data(amount=amount)
    
    data = await state.get_data()
    hint = data.get("requisites_hint", "Введите реквизиты:")
    
    await state.set_state(RequestCreation.entering_requisites)
    await message.answer(
        f"💳 <b>Шаг 4.</b> {hint}",
        parse_mode="HTML"
    )


# ── Step 4: Enter Requisites ──────────────────────────────────────────────

@router.message(RequestCreation.entering_requisites)
async def requisites_entered(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not raw:
        await message.answer("❌ Реквизиты не могут быть пустыми. Введите текст:")
        return

    is_valid, formatted, error_msg = parse_card_input(raw)
    
    if not is_valid:
        await message.answer(error_msg, parse_mode="HTML")
        return

    await state.update_data(requisites=formatted)
    await _go_to_confirmation(message, state)


# ── Step 5: Confirmation ──────────────────────────────────────────────────

@router.callback_query(RequestCreation.confirming, F.data == "confirm_submit")
async def confirm_submit(callback: CallbackQuery, state: FSMContext, sheets: SheetsService):
    user_id = callback.from_user.id

    # Double-click guard
    async with _submit_lock:
        if user_id in _submitting_users:
            await callback.answer("⏳ Заявка уже отправляется...", show_alert=True)
            return
        _submitting_users.add(user_id)

    try:
        # Acknowledge immediately to prevent Telegram "query is too old" timeout
        # which happens during slow Google API retries.
        await callback.answer()
        data = await state.get_data()

        # Validate user is still in Sheets
        users = await asyncio.to_thread(sheets.get_users)
        if data["employee_name"] not in users:
            await callback.message.edit_text(
                f"❌ Пользователь '<b>{data['employee_name']}</b>' отсутствует в списке сотрудников.\n\n"
                "Пожалуйста, обновите профиль: /start",
                parse_mode="HTML",
            )
            await callback.message.answer("Выберите действие:", reply_markup=main_menu_kb())
            await state.clear()
            return

        # Remove buttons immediately (anti-double-click)
        await callback.message.edit_text(
            _build_confirmation_text(data) + "\n\n⏳ <i>Отправка в таблицы...</i>",
            parse_mode="HTML",
        )

        project = data.get("project", "A.M. Maison")
        comment = data["requisites"]

        # ── Dual write: ДДС + Оплаты (sequential to avoid SSL thread-safety issues) ─────────────────────────
        dds_result = await asyncio.to_thread(
            sheets.append_to_dds,
            date=data["date"],
            operation_type=data["operation_type"],
            amount=data["amount"],
            employee_name=data["employee_name"],
            project=project,
            period=data["period"],
            comment=comment,
        )

        payments_result = await asyncio.to_thread(
            sheets.append_to_payments,
            project_name=project,
            date=data["date"],
            operation_type=data["operation_type"],
            amount=data["amount"],
            employee_name=data["employee_name"],
            requisites=comment,
            period=data.get("period", ""),
        )

        dds_ok = isinstance(dds_result, dict)
        payments_ok = isinstance(payments_result, dict)
        payments_sheet_missing = payments_result is False
        
        status = "sent" if dds_ok else "error"

        if dds_ok:
            updated_range = dds_result.get("updatedRange", "неизвестно")
            await db.save_request(
                telegram_id=user_id,
                employee_name=data["employee_name"],
                date=data["date"],
                operation_type=data["operation_type"],
                amount=data["amount"],
                project=project,
                period=data["period"],
                comment=comment,
                status=status,
            )
            
            if payments_ok:
                payments_note = f"✅ Таблица «Оплаты» (лист <b>{project}</b>): записано"
            elif payments_sheet_missing:
                payments_note = (f"⚠️ Таблица «Оплаты»: лист <b>{project}</b> не создан.\n📌 Создайте лист с названием <code>{project}</code> в таблице Оплаты")
            else:
                payments_note = f"❌ Таблица «Оплаты» (лист <b>{project}</b>): ошибка записи"

            await callback.message.edit_text(
                f"✅ <b>Заявка успешно добавлена!</b>\n\n"
                f"✅ ДДС (Общая таблица): {updated_range}\n"
                f"{payments_note}\n\n"
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
                project=project,
                period=data["period"],
                comment=comment,
                status=status,
            )
            await callback.message.edit_text(
                "❌ Не удалось добавить заявку в таблицу ДДС.\n"
                "Попробуйте позже или обратитесь к администратору."
            )

    except Exception as e:
        logger.error("Error in confirm_submit: %s", e, exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла непредвиденная ошибка при отправке заявки."
        )
    finally:
        async with _submit_lock:
            _submitting_users.discard(user_id)


# ── Edit flow ──────────────────────────────────────────────────────────────

@router.callback_query(RequestCreation.confirming, F.data == "edit_request")
async def edit_request(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(RequestCreation.editing_field)
    await callback.message.edit_text(
        "✏️ Что хотите изменить?", reply_markup=edit_field_kb(has_project_choice="project" in data)
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
        operations = await _get_operations(callback.from_user.id, sheets)
        await state.set_state(RequestCreation.choosing_operation)
        await callback.message.edit_text(
            "Выберите новый тип операции:", reply_markup=operations_kb(operations)
        )
    elif field == "amount":
        await state.set_state(RequestCreation.entering_amount)
        await callback.message.edit_text("💰 Введите новую сумму:")
    elif field == "project":
        data = await state.get_data()
        op_name = data.get("operation_type")
        
        if op_name:
            projects = await asyncio.to_thread(
                sheets.get_projects_for_operation, 
                op_name
            )
            if projects:
                await state.set_state(RequestCreation.choosing_project)
                await callback.message.edit_text(
                    "🏢 Выберите проект:", reply_markup=projects_kb(projects)
                )
                await callback.answer()
                return

        await callback.answer("⚠️ Невозможно изменить проект.", show_alert=True)
        return
        
    elif field == "requisites":
        await state.set_state(RequestCreation.entering_requisites)
        data = await state.get_data()
        hint = data.get("requisites_hint", "Введите реквизиты:")
        await callback.message.edit_text(f"💳 {hint}")

    await callback.answer()


# ── Cancel request ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_request", StateFilter("*"))
async def cancel_request(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Заявка отменена.")
    await callback.message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await callback.answer()
