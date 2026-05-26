"""Handlers for /start, registration, main menu, profile, and help."""

import asyncio
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import database as db
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


@router.callback_query(Registration.waiting_for_name, F.data.startswith("user:"))
async def process_name(callback: CallbackQuery, state: FSMContext):
    """Save user name and complete registration."""
    name = callback.data.split(":", 1)[1]

    await db.create_user(callback.from_user.id, name)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Отлично, {name}! Вы зарегистрированы."
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
    await message.answer(
        "ℹ️ <b>Справка</b>\n\n"
        "Этот бот добавляет финансовые заявки в таблицу ДДС.\n\n"
        "<b>Как создать заявку:</b>\n"
        "1. Нажмите «📝 Создать заявку»\n"
        "2. Выберите тип операции\n"
        "3. Введите сумму\n"
        "4. Выберите проект\n"
        "5. Введите комментарий\n"
        "6. Проверьте данные и подтвердите\n\n"
        "Заявка будет добавлена в Google Таблицу.\n\n"
        "<b>Команды:</b>\n"
        "/start — Главное меню\n"
        "/cancel — Отменить текущее действие",
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


# ── Clear (Admin only) ─────────────────────────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: Message, state: FSMContext, sheets: SheetsService):
    # Разрешаем только определенному пользователю (замените ID если нужно)
    ADMIN_ID = 553623285
    if message.from_user.id != ADMIN_ID:
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
