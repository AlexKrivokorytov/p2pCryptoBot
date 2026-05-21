"""Marketplace handlers — Ad browsing and Ad creation FSM wizard."""

from __future__ import annotations

import math
import re
from typing import Any

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    ad_confirm_keyboard,
    ad_type_keyboard,
    asset_keyboard,
    back_to_menu_keyboard,
    network_selection_keyboard,
)
from db.models.user import User
from services.marketplace_service import MarketplaceService
from services.wallet_service import get_supported_chains_for_asset

log = structlog.get_logger(__name__)
router = Router(name="marketplace")

# ── Constants ──────────────────────────────────────────────────────────────────
PAGE_SIZE = 5
FIAT_RE = re.compile(r"^[A-Z]{2,5}$")  # e.g. RUB, USD, EUR


# ── FSM States ─────────────────────────────────────────────────────────────────


class CreateAdFSM(StatesGroup):
    """Wizard states for creating a P2P advertisement."""

    choosing_type = State()
    choosing_asset = State()
    choosing_network = State()
    entering_fiat = State()
    entering_price = State()
    entering_limits = State()
    confirming = State()


# ── Helper: build ad list page ─────────────────────────────────────────────────


# ── Helper: build ad list page ─────────────────────────────────────────────────


def _build_ad_list_text(ads: list[Any], page: int, total_pages: int) -> str:
    """Build the formatted text block for an ads page."""
    if not ads:
        return "😔 <b>No active ads found.</b>\n\nBe the first — create your own!"

    lines = ["🛒 <b>P2P Market</b>\n"]
    for i, ad in enumerate(ads, start=1):
        # ad is a model instance but we treat it as having these attrs
        is_sell = getattr(ad, "type", "sell") == "sell"
        emoji = "📤" if is_sell else "📥"
        direction = "Sell" if is_sell else "Buy"
        network_str = f" ({ad.chain.upper()})" if ad.chain else ""
        lines.append(
            f"{i}. {emoji} <b>{direction} {ad.asset}</b>{network_str} for <b>{ad.fiat}</b>\n"
            f"   Rate: <b>{float(ad.price_value):.2f} {ad.fiat}/{ad.asset}</b>\n"
            f"   Limits: <b>{float(ad.min_limit):.0f} – {float(ad.max_limit):.0f} {ad.fiat}</b>\n"
        )
    lines.append(f"\n📄 Page {page}/{total_pages}")
    return "\n".join(lines)


def _build_ad_page_keyboard(ads: list[Any], page: int, total_pages: int) -> Any:
    """Build inline keyboard with ad buttons and pagination."""
    builder = InlineKeyboardBuilder()
    for i, ad in enumerate(ads, start=1):
        is_sell = getattr(ad, "type", "sell") == "sell"
        emoji = "📤" if is_sell else "📥"
        direction = "Sell" if is_sell else "Buy"
        builder.row(
            InlineKeyboardButton(
                text=f"{emoji} #{i} {direction} {ad.asset} @ {float(ad.price_value):.2f} {ad.fiat}",
                callback_data=f"ad:view:{ad.id}",
            )
        )

    # Pagination row
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"market:page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️ Next", callback_data=f"market:page:{page + 1}"))
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="➕ Create Ad", callback_data="ad:create"),
        InlineKeyboardButton(text="🏠 Menu", callback_data="menu:main"),
    )
    return builder.as_markup()


# ── Browse market ──────────────────────────────────────────────────────────────


async def _render_market(
    callback: CallbackQuery, session: AsyncSession, page: int, db_user: User
) -> None:
    """Fetch and render ads for the given page.

    Args:
        callback: The triggering callback query.
        session: DB session.
        page: Page number (1-indexed).
        db_user: Current user object for fiat filtering.
    """
    all_ads = await MarketplaceService.get_all_active_ads(session, fiat=db_user.default_fiat)

    total_pages = max(1, math.ceil(len(all_ads) / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    paginated = list(all_ads)[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    text = _build_ad_list_text(list(paginated), page, total_pages)
    keyboard = _build_ad_page_keyboard(list(paginated), page, total_pages)

    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "market:browse")
async def cb_market_browse(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Show the P2P market order book — first page."""
    await _render_market(callback, session, page=1, db_user=db_user)


@router.callback_query(F.data.startswith("market:page:"))
async def cb_market_page(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Paginate through the ad list."""
    page = int(callback.data.split(":")[-1])  # type: ignore[union-attr]
    await _render_market(callback, session, page=page, db_user=db_user)


@router.callback_query(F.data.startswith("ad:view:"))
async def cb_ad_view(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show details for a single ad."""
    ad_id = int(callback.data.split(":")[-1])  # type: ignore[union-attr]
    ad = await MarketplaceService.get_ad_details(session, ad_id=ad_id)

    if ad is None:
        await callback.answer("❌ Ad not found.", show_alert=True)
        return

    emoji = "📤" if ad["type"] == "sell" else "📥"
    direction = "Sell" if ad["type"] == "sell" else "Buy"
    terms_text = ad["terms"] or "No special terms."

    network_str = f" (Network: <b>{ad['chain'].upper()}</b>)" if ad.get("chain") else ""
    text = (
        f"📋 <b>Ad Details</b>\n\n"
        f"{emoji} Direction: <b>{direction} {ad['asset']}</b>{network_str}\n"
        f"💵 Fiat: <b>{ad['fiat']}</b>\n"
        f"📈 Rate: <b>{ad['price_value']:.2f} {ad['fiat']}/{ad['asset']}</b>\n"
        f"🔢 Limits: <b>{ad['min_limit']:.0f} – {ad['max_limit']:.0f} {ad['fiat']}</b>\n\n"
        f"📝 Terms: {terms_text}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Accept Trade", callback_data=f"trade:take_ad:{ad_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Back to Market", callback_data="market:browse"))

    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    """No-op for pagination label buttons."""
    await callback.answer()


# ── Create Ad FSM Wizard ───────────────────────────────────────────────────────


@router.callback_query(F.data == "ad:create")
async def cb_ad_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Entry point for Ad creation wizard — choose type."""
    await state.set_state(CreateAdFSM.choosing_type)
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "📝 <b>Create New Ad</b>\n\nWhat do you want to do?",
            reply_markup=ad_type_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("adtype:"), CreateAdFSM.choosing_type)
async def cb_ad_choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Save the ad type (buy/sell) and ask for the crypto asset."""
    ad_type_str = callback.data.split(":")[-1]  # type: ignore[union-attr]
    await state.update_data(ad_type=ad_type_str)
    await state.set_state(CreateAdFSM.choosing_asset)

    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "🪙 <b>Step 1/5</b> — Choose the crypto asset:",
            reply_markup=asset_keyboard(prefix="ad_asset"),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("ad_asset:"), CreateAdFSM.choosing_asset)
async def cb_ad_choose_asset(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    """Save the asset and ask for network (if multiple) or fiat currency."""
    asset = callback.data.split(":")[-1]  # type: ignore[union-attr]
    await state.update_data(asset=asset)

    chains = get_supported_chains_for_asset(asset)

    if len(chains) > 1:
        await state.set_state(CreateAdFSM.choosing_network)
        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"🌐 <b>Step 1.1</b> — Choose the network for <b>{asset}</b>:",
                reply_markup=network_selection_keyboard(chains),
                parse_mode="HTML",
            )
    else:
        # Only one chain or unknown, skip network selection
        network = chains[0] if chains else "unknown"
        await state.update_data(network=network)
        await state.set_state(CreateAdFSM.entering_fiat)

        if callback.message and isinstance(callback.message, Message):
            fiat_prompt = (
                "💵 <b>Step 2/5</b> — Enter fiat currency code\n\n"
                f"Suggested: <code>{db_user.default_fiat}</code>"
            )
            await callback.message.edit_text(
                fiat_prompt,
                reply_markup=back_to_menu_keyboard(),
                parse_mode="HTML",
            )
    await callback.answer()


@router.callback_query(F.data.startswith("ad_network:"), CreateAdFSM.choosing_network)
async def cb_ad_choose_network(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    """Save the selected network and proceed to fiat entry."""
    network = callback.data.split(":")[-1]  # type: ignore[union-attr]
    await state.update_data(network=network)
    await state.set_state(CreateAdFSM.entering_fiat)

    if callback.message and isinstance(callback.message, Message):
        fiat_prompt = (
            "💵 <b>Step 2/5</b> — Enter fiat currency code\n\n"
            f"Suggested: <code>{db_user.default_fiat}</code>"
        )
        await callback.message.edit_text(
            fiat_prompt,
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "ad:back_to_asset", CreateAdFSM.choosing_network)
async def cb_ad_back_to_asset(callback: CallbackQuery, state: FSMContext) -> None:
    """Go back to asset selection from network selection."""
    await state.set_state(CreateAdFSM.choosing_asset)
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "🪙 <b>Step 1/5</b> — Choose the crypto asset:",
            reply_markup=asset_keyboard(prefix="ad_asset"),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(CreateAdFSM.entering_fiat)
async def msg_ad_enter_fiat(message: Message, state: FSMContext) -> None:
    """Validate and save the fiat currency code."""
    fiat = (message.text or "").strip().upper()
    if not FIAT_RE.match(fiat):
        invalid_msg = (
            "⚠️ Invalid currency code. "
            "Please enter a 3-letter code like <code>RUB</code> or <code>USD</code>."
        )
        await message.answer(invalid_msg, parse_mode="HTML")
        return

    data = await state.get_data()
    asset = data.get("asset", "USDT")
    await state.update_data(fiat=fiat)
    await state.set_state(CreateAdFSM.entering_price)

    await message.answer(
        f"💰 <b>Step 3/5</b> — Enter your price per 1 <b>{asset}</b> in <b>{fiat}</b>:",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(CreateAdFSM.entering_price)
async def msg_ad_enter_price(message: Message, state: FSMContext) -> None:
    """Validate and save the price, then ask for limits."""
    try:
        price = float((message.text or "").strip().replace(",", "."))
        if price <= 0:
            raise ValueError("Price must be positive")
    except ValueError:
        await message.answer(
            "⚠️ Invalid price. Please enter a positive number.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    fiat = data.get("fiat", "RUB")
    await state.update_data(price=price)
    await state.set_state(CreateAdFSM.entering_limits)

    await message.answer(
        f"🔢 <b>Step 4/5</b> — Enter trade limits in <b>{fiat}</b>.\n\n"
        f"Format: <code>min max</code> (e.g. <code>1000 50000</code>):",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(CreateAdFSM.entering_limits)
async def msg_ad_enter_limits(message: Message, state: FSMContext) -> None:
    """Validate and save trade limits, then show confirmation."""
    parts = (message.text or "").strip().split()
    try:
        if len(parts) != 2:
            raise ValueError("Must have exactly 2 values")
        min_limit = float(parts[0].replace(",", "."))
        max_limit = float(parts[1].replace(",", "."))
        if min_limit <= 0 or max_limit <= 0 or min_limit >= max_limit:
            raise ValueError("Invalid range")
    except ValueError:
        await message.answer(
            "⚠️ Invalid limits. Format: <code>min max</code>, e.g. <code>1000 50000</code>.\n"
            "Both must be positive and min must be less than max.",
            parse_mode="HTML",
        )
        return

    await state.update_data(min_limit=min_limit, max_limit=max_limit)
    await state.set_state(CreateAdFSM.confirming)

    data = await state.get_data()
    ad_type = data.get("ad_type", "sell_crypto")
    direction = "📤 Sell crypto" if ad_type == "sell_crypto" else "📥 Buy crypto"
    network = data.get("network", "unknown")

    text = (
        f"✅ <b>Review your Ad</b>\n\n"
        f"Direction: <b>{direction}</b>\n"
        f"Asset: <b>{data['asset']}</b> (Network: <b>{network.upper()}</b>)\n"
        f"Fiat: <b>{data['fiat']}</b>\n"
        f"Rate: <b>{data['price']:.2f} {data['fiat']}/{data['asset']}</b>\n"
        f"Limits: <b>{min_limit:.0f} – {max_limit:.0f} {data['fiat']}</b>\n\n"
        f"Publish this ad?"
    )
    await message.answer(text, reply_markup=ad_confirm_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "ad:confirmed", CreateAdFSM.confirming)
async def cb_ad_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Save the ad to DB and notify the user."""
    data = await state.get_data()
    await state.clear()

    if not callback.from_user:
        await callback.answer("❌ Could not identify user.", show_alert=True)
        return

    # Map FSM type string → AdType
    from db.models.marketplace import AdType, PriceType

    ad_type_map = {"sell_crypto": AdType.sell, "buy_crypto": AdType.buy}
    ad_type = ad_type_map.get(data.get("ad_type", "sell_crypto"), AdType.sell)

    try:
        async with session.begin():
            ad = await MarketplaceService.create_ad(
                session=session,
                maker_id=callback.from_user.id,
                ad_type=ad_type,
                asset=data["asset"],
                fiat=data["fiat"],
                price_type=PriceType.fixed,
                price_value=float(data["price"]),
                min_limit=float(data["min_limit"]),
                max_limit=float(data["max_limit"]),
                payment_method_ids="",  # Will be extended in Phase 4
                chain=data.get("network"),
            )
        log.info(
            "ad_created",
            user_id=callback.from_user.id,
            ad_id=ad.id,
            step="ad_create",
            status="ok",
        )
    except Exception as exc:
        log.error("ad_create_failed", user_id=callback.from_user.id, error=str(exc))
        await callback.answer("⚠️ Failed to publish ad. Try again.", show_alert=True)
        return

    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "🎉 <b>Ad published!</b>\n\nYour ad is now visible in the P2P Market.",
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer("✅ Published!")


@router.callback_query(F.data == "ad:cancel")
async def cb_ad_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the ad creation wizard at any step."""
    await state.clear()
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "❌ Ad creation cancelled.",
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()
