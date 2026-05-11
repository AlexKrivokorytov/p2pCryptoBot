"""Handlers for B2B SaaS lifecycle — license purchase and management."""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import b2b_menu_keyboard, b2b_purchase_keyboard
from services import b2b_service
from services.bot_spawner import BotSpawnerService

log = structlog.get_logger(__name__)
router = Router(name="b2b")


class B2BStates(StatesGroup):
    """States for B2B white-label configuration."""

    waiting_for_token = State()
    waiting_for_branding = State()


@router.callback_query(F.data == "b2b:menu")
async def cb_b2b_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the B2B SaaS main menu."""
    license_data = await b2b_service.get_active_license(session, callback.from_user.id)
    has_active_license = license_data is not None
    license_id = license_data["license_id"] if license_data else None

    text = (
        "💎 <b>White-Label P2P SaaS</b>\n\n"
        f"License ID: <code>{license_id or 'N/A'}</code>\n"
        f"Status: {'✅ Active' if has_active_license else '❌ Inactive'}\n\n"
        "Start your own P2P exchange in minutes. Our SaaS solution provides:\n"
        "• 🚀 <b>Instant Deployment</b>: Your own bot instance\n"
        "• 🎨 <b>Custom Branding</b>: Your name, your rules\n"
        "• 💸 <b>Revenue</b>: Keep 100% of your platform fees\n"
        "• 🔒 <b>Escrow</b>: Secure trades powered by our infrastructure\n\n"
    )

    if has_active_license:
        expires_str = license_data["expires_at"].strftime("%Y-%m-%d") if license_data else ""
        text += f"✅ <b>Active License</b>\nExpires: <code>{expires_str}</code>"
    else:
        text += "❌ No active license found."

    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=b2b_menu_keyboard(has_active_license=has_active_license),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "b2b:buy")
async def cb_b2b_buy(callback: CallbackQuery) -> None:
    """Show purchase options for B2B license."""
    await callback.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>Select Payment Method</b>\n\n"
        "A 1-year White-Label license costs <b>100 Stars</b> (XTR).\n"
        "Alternatively, pay with TON (coming soon).",
        reply_markup=b2b_purchase_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "b2b:pay:stars")
async def cb_b2b_pay_stars(callback: CallbackQuery) -> None:
    """Send Telegram Stars invoice for the B2B license."""
    # 10000 = 100 XTR (Stars use 2 decimal places in some contexts, but check docs)
    # Actually, 1 Star = 100 in amount for XTR? No, check docs.
    # "amount" is in the smallest units of the currency. For XTR, 1 star = 1 unit.
    # Wait, some docs say stars have no decimals, some say 2.
    # Let's use the settings value.
    price = settings.B2B_LICENSE_PRICE_STARS

    prices = [LabeledPrice(label="1-Year White-Label License", amount=price)]

    await callback.message.answer_invoice(  # type: ignore[union-attr]
        title="P2P Escrow White-Label License",
        description="1-year unlimited usage, custom branding, managed hosting.",
        payload="b2b_license_1y",
        provider_token="",  # Empty for Telegram Stars
        currency="XTR",
        prices=prices,
        start_parameter="b2b_buy",
    )
    await callback.answer()


@router.pre_checkout_query()
async def cb_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    """Answer pre-checkout query to allow payment to proceed."""
    # In a real app, you'd check stock or other conditions here.
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def msg_successful_payment(message: Message, session: AsyncSession) -> None:
    """Handle successful payment for B2B license."""
    if not message.from_user or not message.successful_payment:
        return

    charge_id = message.successful_payment.telegram_payment_charge_id
    user_id = message.from_user.id

    # Create license in DB
    new_license = await b2b_service.create_b2b_license(
        session, user_id=user_id, charge_id=charge_id
    )

    log.info(
        "b2b_payment_successful",
        user_id=user_id,
        charge_id=charge_id,
        license_id=new_license["license_id"],
    )

    await message.answer(
        "🎉 <b>Success!</b>\n\n"
        "Your White-Label license has been activated.\n"
        f"Valid until: <code>{new_license['expires_at'].strftime('%Y-%m-%d')}</code>\n\n"
        "You can now spawn your own bot instance from the B2B menu.",
        reply_markup=b2b_menu_keyboard(has_active_license=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "b2b:pay:ton")
async def cb_b2b_pay_ton(callback: CallbackQuery, session: AsyncSession) -> None:
    """Create TON invoice and show payment instructions."""
    amount_ton = await b2b_service.get_ton_license_price()

    invoice = await b2b_service.create_ton_invoice(session, callback.from_user.id, amount_ton)

    text = (
        "🔷 <b>Pay with TON</b>\n\n"
        f"Send exactly: <code>{amount_ton}</code> TON\n"
        f"To address: <code>{settings.MASTER_TON_WALLET}</code>\n"
        f"Required Comment: <code>{invoice['memo']}</code>\n\n"
        "⚠️ <b>IMPORTANT:</b> You MUST include the comment above. "
        "Our scanner uses it to identify your payment automatically.\n\n"
        "<i>License will be activated within 2-5 minutes after transaction is confirmed.</i>"
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=b2b_menu_keyboard(has_active_license=False),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "b2b:spawn")
async def cb_b2b_spawn(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt user for their bot token."""
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🚀 <b>Spawn Your Bot</b>\n\n"
        "To start your own P2P bot, you need a token from @BotFather.\n\n"
        "1. Open @BotFather\n"
        "2. Create a new bot or get token for existing one\n"
        "3. Paste the token here:\n\n"
        "<i>Note: Your token is stored encrypted and only used to run your instance.</i>",
        parse_mode="HTML",
    )
    await state.set_state(B2BStates.waiting_for_token)
    await callback.answer()


@router.message(B2BStates.waiting_for_token)
async def msg_b2b_token(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot_spawner: BotSpawnerService,
) -> None:
    """Collect and validate bot token, then spawn instance."""
    if not message.from_user:
        return
    token = message.text
    if not token or ":" not in token:
        await message.answer("❌ Invalid token format. Please send a valid token from @BotFather.")
        return

    # Find active license
    license_data = await b2b_service.get_active_license(session, message.from_user.id)
    if not license_data:
        await message.answer("❌ You don't have an active license. Please buy one first.")
        await state.clear()
        return

    license_id = license_data["license_id"]

    try:
        # Update and spawn
        await bot_spawner.update_bot_token(session, license_id, token)
        await message.answer(
            "✅ <b>Bot Spawned!</b>\n\n"
            "Your white-label instance is now running.\n"
            "Try sending /start to your bot to verify.",
            reply_markup=b2b_menu_keyboard(has_active_license=True),
            parse_mode="HTML",
        )
        await state.clear()
    except Exception as e:
        log.error("b2b_spawn_handler_failed", error=str(e), user_id=message.from_user.id)
        msg = (
            "❌ <b>Deployment Failed</b>\n\n"
            "Could not start your bot. Please check if the token is correct."
        )
        await message.answer(msg)
