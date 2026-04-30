"""Wallet handlers — generate, view and check balances of on-chain wallets."""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    WALLET_CHAIN_LABELS,
    back_to_menu_keyboard,
    wallet_actions_keyboard,
    wallet_chain_keyboard,
)
from services import balance_service, wallet_service
from utils.formatters import format_error

log = structlog.get_logger(__name__)
router = Router(name="wallet")


# ── Text builders ──────────────────────────────────────────────────────────────


async def _build_wallet_text(session: AsyncSession, user_id: int) -> str:
    """Build the wallet overview text (addresses only, no balance)."""
    wallets = await wallet_service.get_user_wallets(session, user_id)
    if wallets:
        lines = ["💼 <b>Your Wallets</b>\n"]
        for w in wallets:
            label = WALLET_CHAIN_LABELS.get(w.chain, w.chain.upper())
            lines.append(f"{label}\n<code>{w.address}</code>\n")
        return "\n".join(lines)
    return (
        "💼 <b>Your Wallets</b>\n\n"
        "You don't have any wallets yet.\n"
        "Choose a network to generate your first wallet:"
    )


async def _build_balance_text(session: AsyncSession, user_id: int) -> str:
    """Build the wallet balance text by querying on-chain balances."""
    portfolio = await balance_service.get_portfolio_balances(session, user_id)

    if not portfolio:
        return (
            "💼 <b>Your Wallets</b>\n\n"
            "You don't have any wallets yet.\n"
            "Choose a network to generate your first wallet:"
        )

    lines = ["💰 <b>Wallet Balances</b>\n"]
    for wb in portfolio:
        label = WALLET_CHAIN_LABELS.get(wb.wallet.chain, wb.wallet.chain.upper())
        short_addr = wb.wallet.address[:8] + "…" + wb.wallet.address[-6:]
        lines.append(f"<b>{label}</b>  <code>{short_addr}</code>")
        if wb.balances:
            for asset, amount in wb.balances.items():
                if amount > 0:
                    lines.append(f"  • {asset}: <b>{amount:.6f}</b>")
                else:
                    lines.append(f"  • {asset}: 0.00")
        else:
            lines.append("  • Balance unavailable")
        lines.append("")

    lines.append("🕐 <i>Updated just now</i>")
    return "\n".join(lines)


# ── Handlers ───────────────────────────────────────────────────────────────────


@router.message(Command("wallet"))
async def cmd_wallet(message: Message, session: AsyncSession) -> None:
    """Show the user's wallets via /wallet command."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    text = await _build_wallet_text(session, user_id)
    await message.answer(text, reply_markup=wallet_actions_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "menu:wallet")
async def cb_wallet(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the user's wallets via inline button."""
    if not isinstance(callback.message, Message):
        return
    user_id = callback.from_user.id
    text = await _build_wallet_text(session, user_id)
    await callback.message.edit_text(
        text, reply_markup=wallet_actions_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "wallet:balance")
async def cb_wallet_balance(callback: CallbackQuery, session: AsyncSession) -> None:
    """Fetch and display on-chain balances for all user wallets."""
    if not isinstance(callback.message, Message):
        return
    user_id = callback.from_user.id

    await callback.message.edit_text(
        "⏳ <b>Fetching balances…</b>\nThis may take a few seconds.",
        parse_mode="HTML",
    )

    log.info(
        "wallet_balance_requested",
        user_id=user_id,
        step="cb_wallet_balance",
    )

    text = await _build_balance_text(session, user_id)
    await callback.message.edit_text(
        text,
        reply_markup=wallet_actions_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "wallet:add")
async def cb_wallet_add(callback: CallbackQuery) -> None:
    """Show chain selector for adding a new wallet."""
    if not isinstance(callback.message, Message):
        return
    await callback.message.edit_text(
        "🔗 <b>Add Wallet</b>\n\nChoose a blockchain network:",
        reply_markup=wallet_chain_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wallet:generate:"))
async def cb_generate_wallet(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Generate a new wallet on the chosen chain."""
    if not callback.data or not isinstance(callback.message, Message):
        return
    chain = callback.data.split(":")[2]
    user_id = callback.from_user.id
    label = WALLET_CHAIN_LABELS.get(chain, chain.upper())

    await callback.message.edit_text(
        f"⏳ Generating your <b>{label}</b> wallet…",
        parse_mode="HTML",
    )

    try:
        async with session.begin():
            wallet = await wallet_service.generate_and_save_wallet(session, user_id, chain)
    except ValueError as exc:
        await callback.message.edit_text(
            format_error(str(exc)),
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"✅ <b>{label} Wallet Created!</b>\n\n"
        f"Address:\n<code>{wallet.address}</code>\n\n"
        "⚠️ <b>Important:</b> Your private key is encrypted and stored securely.\n"
        "Never share your private key with anyone.",
        reply_markup=wallet_actions_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
