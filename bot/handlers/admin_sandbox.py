"""Handlers for the Admin Sandbox (Debug) menu."""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import admin_sandbox_keyboard, admin_sandbox_order_status_keyboard
from bot.states import AdminSandboxFSM
from services import admin_sandbox_service

log = structlog.get_logger(__name__)
router = Router(name="admin_sandbox")


def _is_admin(user_id: int) -> bool:
    """Check if user_id is in ADMIN_IDS."""
    return user_id in settings.ADMIN_IDS


@router.callback_query(F.data == "admin:sandbox:menu")
async def cb_sandbox_menu(callback: CallbackQuery) -> None:
    """Show the Admin Sandbox menu."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("🚫 Unauthorized.", show_alert=True)
        return

    text = (
        "🛠️ <b>Admin Sandbox (Debug)</b>\n\n"
        "Use these tools to test platform features without costs:\n"
        "• 💎 <b>Activate License</b>: Instant 1-year B2B license\n"
        "• 💰 <b>Add Test USDT</b>: Inject 10,000 USDT to your profile\n"
        "• ⚙️ <b>Order States</b>: (Coming soon) Force specific states\n\n"
        "⚠️ <b>WARNING:</b> These actions mutate the live database."
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=admin_sandbox_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:sandbox:lic_bypass")
async def cb_sandbox_lic_bypass(callback: CallbackQuery, session: AsyncSession) -> None:
    """Instantly activate a B2B license for the current admin."""
    if not _is_admin(callback.from_user.id):
        return

    lic = await admin_sandbox_service.activate_license_bypass(
        session, admin_id=callback.from_user.id, user_id=callback.from_user.id
    )

    await callback.message.answer(  # type: ignore[union-attr]
        f"✅ <b>License Activated!</b>\n"
        f"ID: <code>{lic.id}</code>\n"
        f"Expires: <code>{lic.expires_at.strftime('%Y-%m-%d')}</code>",
        parse_mode="HTML",
    )
    await callback.answer("License bypassed!")


@router.callback_query(F.data == "admin:sandbox:add_usdt")
async def cb_sandbox_add_usdt(callback: CallbackQuery, session: AsyncSession) -> None:
    """Inject test balance for the current admin."""
    if not _is_admin(callback.from_user.id):
        return

    await admin_sandbox_service.inject_test_balance(
        session, admin_id=callback.from_user.id, user_id=callback.from_user.id, amount=10000.0
    )

    await callback.message.answer(  # type: ignore[union-attr]
        "💰 <b>Test USDT Injected!</b>\n10,000 USDT added to your test profile.",
        parse_mode="HTML",
    )
    await callback.answer("Balance injected!")


# ── Order State Forcing ────────────────────────────────────────────────────────


@router.callback_query(F.data == "admin:sandbox:order_state")
async def cb_sandbox_order_state(callback: CallbackQuery, state: FSMContext) -> None:
    """Step 1: Start order state forcing flow."""
    if not _is_admin(callback.from_user.id):
        return

    await state.set_state(AdminSandboxFSM.enter_order_id)
    await callback.message.answer(  # type: ignore[union-attr]
        "⚙️ <b>Sandbox: Force Order State</b>\n\nEnter the <b>Order ID</b> you want to modify:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminSandboxFSM.enter_order_id)
async def msg_sandbox_order_id(message: Message, state: FSMContext) -> None:
    """Step 2: Received Order ID, show status selection."""
    order_id = (message.text or "").strip()
    if len(order_id) < 8:
        await message.answer("❌ Invalid Order ID. Please enter at least 8 characters.")
        return

    await state.update_data(sandbox_order_id=order_id)
    await state.set_state(AdminSandboxFSM.choose_status)
    await message.answer(
        f"Order: <code>{order_id}</code>\n\nSelect the target status:",
        reply_markup=admin_sandbox_order_status_keyboard(order_id),
        parse_mode="HTML",
    )


@router.callback_query(AdminSandboxFSM.choose_status, F.data.startswith("admin:sandbox:force:"))
async def cb_sandbox_force_status(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Step 3: Execute status forcing."""
    parts = callback.data.split(":")  # type: ignore[union-attr]
    # admin:sandbox:force:<order_id>:<status>
    order_id = parts[3]
    new_status = parts[4]

    await admin_sandbox_service.force_order_status(
        session, admin_id=callback.from_user.id, order_id=order_id, new_status=new_status
    )

    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>Order state forced!</b>\n"
        f"ID: <code>{order_id}</code>\n"
        f"New Status: <b>{new_status.upper()}</b>",
        reply_markup=admin_sandbox_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("Status forced.")
