"""Create Ad FSM handlers + Order Book browsing — full Maker flow."""

from __future__ import annotations

from decimal import Decimal

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    ad_confirm_keyboard,
    ad_type_keyboard,
    asset_keyboard,
    back_to_menu_keyboard,
    order_book_keyboard,
    order_detail_keyboard,
    payment_keyboard,
    payment_method_keyboard,
)
from bot.states import BrowseOrderBookFSM, CreateAdFSM
from db.models.order import OrderType, SupportedAsset
from providers.crypto_pay import CryptoPayClient
from services import order_service, rate_service
from utils.formatters import format_error

log = structlog.get_logger(__name__)
router = Router(name="order")


# ═══════════════════════════════════════════════════════════════════════════════
# CREATE AD (Maker flow)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Step 1: choose type (sell_crypto or buy_crypto) ────────────────────────────


@router.callback_query(F.data == "ad:create")
async def cb_ad_create(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt ad type selection to start creating a new ad."""
    await state.set_state(CreateAdFSM.choose_type)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "📝 <b>Create Ad</b>\n\nWhat would you like to do?",
        reply_markup=ad_type_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step 2: type chosen → choose asset ─────────────────────────────────────────


@router.callback_query(CreateAdFSM.choose_type, F.data.startswith("adtype:"))
async def cb_ad_type_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    """Store chosen order type, prompt for crypto asset."""
    order_type = callback.data.split(":")[1]  # type: ignore[union-attr]
    try:
        OrderType(order_type)
    except ValueError:
        await callback.answer(f"Unknown type: {order_type}", show_alert=True)
        return

    type_label = "sell" if order_type == "sell_crypto" else "buy"
    await state.update_data(order_type=order_type)
    await state.set_state(CreateAdFSM.choose_asset)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"📈 You want to <b>{type_label} crypto</b>.\n\nChoose the asset:",
        reply_markup=asset_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step 3: asset chosen → enter amount ────────────────────────────────────────


@router.callback_query(CreateAdFSM.choose_asset, F.data.startswith("asset:"))
async def cb_asset_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    """Store chosen asset, prompt for crypto amount."""
    asset = callback.data.split(":")[1]  # type: ignore[union-attr]
    try:
        SupportedAsset(asset)
    except ValueError:
        await callback.answer(f"Unknown asset: {asset}", show_alert=True)
        return

    await state.update_data(asset=asset)
    await state.set_state(CreateAdFSM.enter_amount)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💰 <b>{asset}</b> selected.\n\nEnter the <b>crypto amount</b>:",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step 4: amount entered → enter fiat currency ──────────────────────────────


@router.message(CreateAdFSM.enter_amount)
async def msg_amount(message: Message, state: FSMContext) -> None:
    """Validate and store crypto amount, prompt for fiat currency."""
    try:
        amount = float(message.text or "")
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            format_error("Please enter a valid positive number."), parse_mode="HTML"
        )
        return

    await state.update_data(amount=amount)
    await state.set_state(CreateAdFSM.enter_fiat_currency)
    await message.answer(
        "🌍 Enter the <b>fiat currency</b> code\n"
        "(e.g. <code>RUB</code>, <code>EUR</code>, <code>USD</code>):",
        parse_mode="HTML",
    )


# ── Step 5: fiat currency entered → enter fiat amount ─────────────────────────


@router.message(CreateAdFSM.enter_fiat_currency)
async def msg_fiat_currency(message: Message, state: FSMContext) -> None:
    """Store fiat currency, prompt for fiat amount."""
    currency = (message.text or "").strip().upper()
    if len(currency) < 2 or len(currency) > 10 or not currency.isalpha():
        await message.answer(
            format_error("Invalid currency code. Example: RUB, EUR, USD"), parse_mode="HTML"
        )
        return

    await state.update_data(fiat_currency=currency)
    await state.set_state(CreateAdFSM.enter_fiat_amount)

    # Fetch Binance reference rate for this asset/fiat pair
    data = await state.get_data()
    asset = data.get("asset", "")
    rate_hint = await rate_service.get_rate_hint_text(asset, currency)

    hint_block = f"\n\n{rate_hint}" if rate_hint else ""
    await message.answer(
        f"💵 Enter the <b>fiat amount</b> in <code>{currency}</code>:{hint_block}",
        parse_mode="HTML",
    )


# ── Step 6: fiat amount entered → choose payment method ───────────────────────


@router.message(CreateAdFSM.enter_fiat_amount)
async def msg_fiat_amount(message: Message, state: FSMContext) -> None:
    """Validate fiat amount, prompt for payment method."""
    try:
        fiat_amount = float(message.text or "")
        if fiat_amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            format_error("Please enter a valid positive fiat amount."), parse_mode="HTML"
        )
        return

    await state.update_data(fiat_amount=fiat_amount)
    await state.set_state(CreateAdFSM.enter_payment_method)
    await message.answer(
        "🏦 Choose a <b>payment method</b>:",
        reply_markup=payment_method_keyboard(),
        parse_mode="HTML",
    )


# ── Step 7: payment method chosen → show summary ──────────────────────────────


@router.callback_query(CreateAdFSM.enter_payment_method, F.data.startswith("paymethod:"))
async def cb_payment_method(callback: CallbackQuery, state: FSMContext) -> None:
    """Store payment method, show ad summary for confirmation."""
    method = callback.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(payment_method=method)

    data = await state.get_data()
    type_label = "📤 Selling" if data["order_type"] == "sell_crypto" else "📥 Buying"

    summary = (
        f"📋 <b>Ad Summary</b>\n\n"
        f"Type: {type_label}\n"
        f"Asset: <code>{data['asset']}</code>\n"
        f"Crypto amount: <code>{data['amount']}</code>\n"
        f"Fiat: <code>{data['fiat_amount']} {data['fiat_currency']}</code>\n"
        f"Payment: <b>{method}</b>\n\n"
        "✅ Confirm to create ad and generate payment link."
    )
    await state.set_state(CreateAdFSM.confirm)
    await callback.message.edit_text(  # type: ignore[union-attr]
        summary, reply_markup=ad_confirm_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


# ── Step 8: confirmed → create order + invoice ─────────────────────────────────


@router.callback_query(CreateAdFSM.confirm, F.data == "ad:confirmed")
async def cb_ad_confirmed(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
) -> None:
    """Create the ad in DB and generate Crypto Pay invoice for Maker."""
    data = await state.get_data()
    await state.clear()
    maker_id = callback.from_user.id

    try:
        result = await order_service.create_order(
            session,
            crypto_pay,
            maker_id=maker_id,
            order_type=data["order_type"],
            asset=data["asset"],
            amount=data["amount"],
            fiat_currency=data["fiat_currency"],
            fiat_amount=data["fiat_amount"],
            payment_method=data["payment_method"],
        )
    except Exception as exc:
        log.error("ad_creation_failed", user_id=maker_id, error=str(exc), step="cb_ad_confirmed")
        await callback.message.edit_text(  # type: ignore[union-attr]
            format_error(str(exc)), parse_mode="HTML"
        )
        await callback.answer()
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>Ad created!</b>\n\n"
        f"Order ID: <code>{result['order_id']}</code>\n\n"
        "💳 Pay the invoice below to fund the escrow.\n"
        "Once paid, your ad will appear in the <b>P2P Market</b>.",
        reply_markup=payment_keyboard(result["payment_url"], result["order_id"]),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Cancel ad creation ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "ad:cancel")
async def cb_cancel_ad(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel ad creation and return to menu."""
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "❌ Ad creation cancelled.",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# ORDER BOOK (Taker browsing)
# ═══════════════════════════════════════════════════════════════════════════════


@router.callback_query(F.data == "market:browse")
async def cb_market_browse(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Show the P2P Market Order Book (page 1)."""
    await state.set_state(BrowseOrderBookFSM.browsing)
    await _show_order_book(callback, session, page=1)


@router.callback_query(F.data.startswith("market:page:"))
async def cb_market_page(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Navigate to a specific Order Book page."""
    page = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    await _show_order_book(callback, session, page=page)


async def _show_order_book(
    callback: CallbackQuery,
    session: AsyncSession,
    page: int,
) -> None:
    """Fetch and display a page of active orders."""
    data = await order_service.get_active_orders(session, page=page)

    if not data["orders"]:
        text = "🛒 <b>P2P Market</b>\n\n📭 No active orders at the moment."
    else:
        text = (
            f"🛒 <b>P2P Market</b> — {data['total_count']} ads available\n\n"
            "Tap an order to view details:"
        )

    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=order_book_keyboard(data["orders"], data["page"], data["total_pages"]),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Order detail view ──────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("order:view:"))
async def cb_order_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Show detailed view of a single order from the Order Book."""
    order_id = callback.data.split(":")[2]  # type: ignore[union-attr]
    order = await order_service.get_order_details(session, order_id=order_id)

    if order is None:
        await callback.answer("Order not found.", show_alert=True)
        return

    type_label = "📤 Selling" if order["order_type"] == "sell_crypto" else "📥 Buying"
    maker_name = order["maker_username"]

    # Price per unit (maker's rate)
    maker_amount = float(order["amount"])
    maker_rate = float(order["fiat_amount"]) / maker_amount if maker_amount else 0.0
    maker_rate_str = f"{maker_rate:,.2f}"

    # Binance market rate comparison (fire-and-forget, non-blocking)
    market_rate = await rate_service.get_market_rate(str(order["asset"]), order["fiat_currency"])
    if market_rate is not None:
        diff_pct = ((Decimal(str(maker_rate)) - market_rate) / market_rate) * 100
        sign = "+" if diff_pct >= 0 else ""
        market_line = (
            f"📊 Market rate: <code>{market_rate:,.2f}</code> {order['fiat_currency']} "
            f"(<i>{sign}{diff_pct:.1f}% vs Binance</i>)\n"
        )
    else:
        market_line = ""

    text = (
        f"📋 <b>Order Detail</b>\n\n"
        f"Type: {type_label}\n"
        f"Asset: <code>{order['asset']}</code>\n"
        f"Amount: <code>{order['amount']:.8g}</code>\n"
        f"Price: <code>{order['fiat_amount']:.2f} {order['fiat_currency']}</code>\n"
        f"Rate: <code>{maker_rate_str}</code> {order['fiat_currency']}/unit\n"
        f"{market_line}"
        f"Payment: <b>{order['payment_method']}</b>\n"
        f"Seller: @{maker_name}\n"
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=order_detail_keyboard(order_id),
        parse_mode="HTML",
    )
    await callback.answer()
