"""Handlers for /start, registration, main menu, profile, and help."""

import asyncio
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import database as db
from bot.config import settings
from bot.keyboards import main_menu_kb, users_kb
from bot.states import Registration
from bot.services.sheets import SheetsService

router = Router()


# ── /start ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, sheets: SheetsService):
    """Handle /start — check registration or begin it."""
    await state.clear()
    user = await db.get_user(message.from_user.id)
    users = await asyncio.to_thread(sheets.get_users)

    if user and user['name'] in users:
        await message.answer(
            f"👋 Привет, {user['name']}! Выберите действие:",
            reply_markup=main_menu_kb(),
        )
    else:
        if not users:
            await message.answer("⚠️ Список сотрудников пуст. Обратитесь к администратору.")
            return

        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Выберите ваше имя из списка:",
            reply_markup=users_kb(users)
        )
        await state.set_state(Registration.waiting_for_name)


@router.message(Command("super_start"))
async def cmd_change_name(message: Message, state: FSMContext, sheets: SheetsService):
    """Force re-registration to change name (Admins only)."""
    if not await db.is_admin(message.from_user.id, settings.developer_ids, getattr(settings, 'owner_id', None)):
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    await state.clear()
    users = await asyncio.to_thread(sheets.get_users)
    
    if not users:
        await message.answer("⚠️ Список сотрудников пуст. Обратитесь к администратору.")
        return

    await message.answer(
        "🔄 Смена имени.\n\n"
        "Выберите ваше новое имя из списка:",
        reply_markup=users_kb(users)
    )
    await state.set_state(Registration.waiting_for_name)


@router.callback_query(Registration.waiting_for_name, F.data.startswith("user:"))
async def process_name(callback: CallbackQuery, state: FSMContext, sheets: SheetsService):
    """Save user name and prompt for position."""
    name = callback.data.split(":", 1)[1]
    await state.update_data(user_name=name)
    
    positions = await asyncio.to_thread(sheets.get_positions)
    if not positions:
        # Fallback if positions column is empty/missing
        await db.create_user(callback.from_user.id, name, "")
        await state.clear()
        await callback.message.edit_text(f"✅ Отлично, {name}! Вы зарегистрированы.")
        await callback.message.answer("Выберите действие:", reply_markup=main_menu_kb())
        await callback.answer()
        return

    await state.set_state(Registration.waiting_for_position)
    
    from bot.keyboards import positions_kb
    await callback.message.edit_text(
        f"👋 Привет, {name}!\n\n"
        "Теперь выберите вашу позицию из списка:",
        reply_markup=positions_kb(positions)
    )
    await callback.answer()


@router.callback_query(Registration.waiting_for_position, F.data.startswith("pos:"))
async def process_position(callback: CallbackQuery, state: FSMContext):
    """Save position and complete registration."""
    position = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    name = data.get("user_name", "Неизвестно")

    await db.create_user(callback.from_user.id, name, position)
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ Отлично, {name}! Вы зарегистрированы как <b>{position}</b>.",
        parse_mode="HTML"
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


# ── Help ───────────────────────────────────────────────────────────────────

@router.message(F.text == "❓ Помощь")
async def show_help(message: Message, state: FSMContext):
    await state.clear()
    is_admin = await db.is_admin(message.from_user.id, settings.developer_ids, getattr(settings, 'owner_id', None))
    admin_section = (
        "\n<b>Команды администратора:</b>\n"
        "/super_start — Изменить свое имя (выбрать заново)\n"
        "/access — Управление доступом пользователей к боту\n"
    ) if is_admin else ""
    dev_section = (
        "\n<b>Команды разработчика:</b>\n"
        "/add_admin — Назначить администратора\n"
        "/remove_admin — Убрать администратора\n"
        "/list_admins — Список администраторов\n"
    ) if message.from_user.id in settings.developer_ids else ""
    await message.answer(
        "ℹ️ <b>Справка</b>\n\n"
        "Бот добавляет финансовые заявки сразу в две таблицы: ДДС и Оплаты.\n\n"
        "<b>Как создать заявку:</b>\n"
        "1. Нажмите «📝 Создать заявку»\n"
        "2. Выберите тип операции\n"
        "3. Выберите проект (если требуется)\n"
        "4. Введите сумму\n"
        "5. Введите реквизиты / назначение\n"
        "6. Проверьте данные и подтвердите\n\n"
        "<b>Основные команды:</b>\n"
        "/start — Главное меню\n"
        "/cancel — Отменить текущее действие"
        + admin_section
        + dev_section,
        parse_mode="HTML",
    )


# ── Cancel ─────────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    await state.clear()
    if current_state:
        await message.answer("❌ Действие отменено.", reply_markup=main_menu_kb())
    else:
        await message.answer("Нечего отменять.", reply_markup=main_menu_kb())


# ── Clear / profile reset (admin or self) ─────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: Message, state: FSMContext, sheets: SheetsService):
    """Reset user profile — allowed for developer and admins."""
    if not await db.is_admin(message.from_user.id, settings.developer_ids, getattr(settings, 'owner_id', None)):
        await message.answer("❌ Нет прав для выполнения команды.")
        return

    users = await asyncio.to_thread(sheets.get_users)
    if not users:
        await message.answer("⚠️ Список сотрудников пуст. Обратитесь к администратору.")
        return

    await state.clear()
    await message.answer(
        "🔄 Сброс профиля.\n\nВыберите ваше новое имя из списка:",
        reply_markup=users_kb(users)
    )
    await state.set_state(Registration.waiting_for_name)
