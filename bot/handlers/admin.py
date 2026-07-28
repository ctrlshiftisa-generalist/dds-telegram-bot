"""Admin management commands — adding projects, entities, and managing admins."""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import database as db
from bot.config import settings
from bot.keyboards import (
    cancel_kb,
    main_menu_kb,
)
from bot.states import AdminManagement

logger = logging.getLogger(__name__)

router = Router()

DEVELOPER_IDS = settings.developer_ids
OWNER_ID = settings.owner_id  # 0 если не задан


# ── Access helpers ────────────────────────────────────────────────────────

def _is_developer_or_owner(telegram_id: int) -> bool:
    """True if the user is the developer or the configured owner."""
    if telegram_id in DEVELOPER_IDS:
        return True
    if OWNER_ID and telegram_id == OWNER_ID:
        return True
    return False


async def _check_admin(message: Message) -> bool:
    """Check admin/developer/owner access. Sends error if denied."""
    if await _has_admin_rights(message.from_user.id):
        return True
    await message.answer("❌ У вас нет прав для выполнения этой команды.")
    return False

async def _has_admin_rights(telegram_id: int) -> bool:
    if _is_developer_or_owner(telegram_id):
        return True
    if await db.is_admin(telegram_id, DEVELOPER_IDS, getattr(settings, 'owner_id', None)):
        return True
    return False


async def _check_developer_or_owner(message: Message) -> bool:
    """Check developer-or-owner access (required for creating/deleting entities and admins)."""
    if _is_developer_or_owner(message.from_user.id):
        return True
    await message.answer("❌ Эта команда доступна только разработчику или овнеру.")
    return False


async def _check_developer(message: Message) -> bool:
    """Check developer-only access (strict, kept for legacy use)."""
    if message.from_user.id in DEVELOPER_IDS:
        return True
    await message.answer("❌ Эта команда доступна только разработчику.")
    return False

from bot.keyboards import users_access_kb

# ── /access ───────────────────────────────────────────────────────────────

@router.message(Command("access"))
async def cmd_access(message: Message):
    """Manage user access (developer/owner/admin only)."""
    if not await _check_admin(message):
        return

    users = await db.get_all_users()
    if not users:
        await message.answer("Список пользователей пуст.")
        return

    await message.answer(
        "👥 <b>Управление доступом к боту:</b>\n"
        "Нажмите на пользователя, чтобы забрать или вернуть доступ.",
        reply_markup=users_access_kb(users),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("toggle_ban:"))
async def toggle_ban_cb(callback: CallbackQuery):
    if not await _has_admin_rights(callback.from_user.id):
        await callback.answer("❌ Нет прав.", show_alert=True)
        return

    target_id = int(callback.data.split(":")[1])
    user = await db.get_user(target_id)
    if not user:
        await callback.answer("❌ Пользователь не найден.", show_alert=True)
        return
        
    # Toggle ban status
    new_status = not user.get("is_banned")
    await db.set_user_ban_status(target_id, new_status)
    
    # Refresh user list
    users = await db.get_all_users()
    await callback.message.edit_reply_markup(reply_markup=users_access_kb(users))
    
    action = "заблокирован 🚫" if new_status else "разблокирован ✅"
    await callback.answer(f"Пользователь {user['name']} {action}", show_alert=True)

# ── /add_admin (developer only) ───────────────────────────────────────────

@router.message(Command("add_admin"))
async def cmd_add_admin(message: Message, state: FSMContext):
    """Appoint a new admin — developer/owner only."""
    if not await _check_developer_or_owner(message):
        return

    await state.set_state(AdminManagement.waiting_new_admin_id)
    await message.answer(
        "👤 Введите Telegram ID пользователя, которого хотите назначить администратором\n"
        "(целое число, например: <code>123456789</code>):",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(AdminManagement.waiting_new_admin_id)
async def admin_new_id_entered(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ Введите корректный Telegram ID (целое число):")
        return

    new_admin_id = int(text)
    if new_admin_id in DEVELOPER_IDS:
        await message.answer("ℹ️ Разработчик уже имеет все права.")
        await state.clear()
        return

    ok = await db.add_admin(new_admin_id, added_by=message.from_user.id)
    await state.clear()
    if ok:
        await message.answer(
            f"✅ Пользователь <code>{new_admin_id}</code> назначен администратором.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(
            f"ℹ️ Пользователь <code>{new_admin_id}</code> уже является администратором.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )


# ── /remove_admin (developer only) ───────────────────────────────────────

@router.message(Command("remove_admin"))
async def cmd_remove_admin(message: Message, state: FSMContext):
    """Remove admin rights — developer/owner only."""
    if not await _check_developer_or_owner(message):
        return

    admins = await db.get_all_admins()
    if not admins:
        await message.answer("Список администраторов пуст.")
        return

    lines = ["👥 <b>Текущие администраторы:</b>\n"]
    for a in admins:
        lines.append(f"• <code>{a['telegram_id']}</code> (добавлен: {a['added_at'][:10]})")
    lines.append("\n✏️ Введите Telegram ID администратора для удаления:")

    await state.set_state(AdminManagement.waiting_remove_admin_id)
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(AdminManagement.waiting_remove_admin_id)
async def admin_remove_id_entered(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ Введите корректный Telegram ID:")
        return

    target_id = int(text)
    ok = await db.remove_admin(target_id)
    await state.clear()
    if ok:
        await message.answer(
            f"✅ Администратор <code>{target_id}</code> удалён.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(
            f"❌ Пользователь <code>{target_id}</code> не найден в списке администраторов.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )


# ── /list_admins (developer only) ────────────────────────────────────────

@router.message(Command("list_admins"))
async def cmd_list_admins(message: Message):
    """List all admins — developer/owner only."""
    if not await _check_developer_or_owner(message):
        return

    admins = await db.get_all_admins()
    if not admins:
        await message.answer("👥 Список администраторов пуст.")
        return

    lines = [f"👥 <b>Администраторы ({len(admins)}):</b>\n"]
    for a in admins:
        lines.append(f"• <code>{a['telegram_id']}</code> — добавлен {a['added_at'][:10]}")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /cancel for admin flows ────────────────────────────────────────────────

@router.callback_query(F.data == "admin_cancel")
async def admin_cancel_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Действие отменено.")
    await callback.message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await callback.answer()
