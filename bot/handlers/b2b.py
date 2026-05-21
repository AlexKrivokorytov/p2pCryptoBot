"""Handlers for B2B SaaS lifecycle — license purchase and management."""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import b2b_menu_keyboard, b2b_purchase_keyboard
from bot.states import B2BCustomizeFSM
from services import b2b_service
from services.bot_spawner import BotSpawnerService

log = structlog.get_logger(__name__)
router = Router(name="b2b")


class B2BStates(StatesGroup):
    """States for B2B white-label configuration."""

    waiting_for_branding = State()


@router.callback_query(F.data == "b2b:menu")
async def cb_b2b_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the B2B SaaS main menu."""
    license_data = await b2b_service.get_active_license(session, callback.from_user.id)
    has_active_license = license_data is not None
    license_id = license_data["license_id"] if license_data else None

    text = (
        "💎 <b>White-Label P2P SaaS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
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


@router.callback_query(F.data == "b2b:customize")
async def cb_b2b_customize(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the branding customization menu."""
    if not isinstance(callback.message, Message):
        return

    license_data = await b2b_service.get_active_license(session, callback.from_user.id)
    if not license_data:
        await callback.answer("❌ Active license required.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏷️ Bot Name", callback_data="b2b:edit:bot.name"),
        InlineKeyboardButton(text="👋 Welcome Msg", callback_data="b2b:edit:bot.welcome_message"),
    )
    builder.row(
        InlineKeyboardButton(text="ℹ️ Help Text", callback_data="b2b:edit:bot.help_text"),
        InlineKeyboardButton(text="📞 Support Handle", callback_data="b2b:edit:bot.support_handle"),
    )
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="b2b:menu"))

    curr_name = license_data["branding"].get("bot", {}).get("name", "N/A")
    await callback.message.edit_text(
        "🎨 <b>Customize Branding</b>\n\n"
        "Select a field to customize. Your changes will be applied instantly.\n\n"
        f"<b>Current Name:</b> <code>{curr_name}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("b2b:edit:"))
async def cb_b2b_customize_field(callback: CallbackQuery, state: FSMContext) -> None:
    """Ask for the new value of a branding field."""
    if not isinstance(callback.message, Message):
        return

    field_path = callback.data.split(":", 2)[2]  # type: ignore[union-attr]
    await state.set_state(B2BCustomizeFSM.enter_value)
    await state.update_data(field_path=field_path)

    prompts = {
        "bot.name": "Enter the new <b>Bot Name</b> (e.g. My P2P Bot):",
        "bot.welcome_message": (
            "Enter the new <b>Welcome Message</b>.\n\n"
            "Tip: Use <code>{bot_name}</code> and <code>{first_name}</code> as placeholders."
        ),
        "bot.help_text": "Enter the new <b>Help Text</b> (HTML supported):",
        "bot.support_handle": "Enter the <b>Support Handle</b> (e.g. @my_support):",
    }

    await callback.message.edit_text(
        prompts.get(field_path, "Enter the new value:"),
        reply_markup=InlineKeyboardBuilder()
        .row(InlineKeyboardButton(text="❌ Cancel", callback_data="b2b:customize"))
        .as_markup(),  # type: ignore[arg-type]
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(B2BCustomizeFSM.enter_value)
async def msg_b2b_branding_value(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Process the new branding value and update DB."""
    data = await state.get_data()
    field_path: str = data["field_path"]
    value = (message.text or "").strip()

    if not value:
        await message.answer("❌ Value cannot be empty.")
        return

    # Basic validation for support handle
    if field_path == "bot.support_handle" and not value.startswith("@"):
        await message.answer("❌ Support handle must start with @")
        return

    try:
        license_data = await b2b_service.get_active_license(session, message.from_user.id)  # type: ignore[union-attr]
        if not license_data:
            await message.answer("❌ License expired or not found.")
            await state.clear()
            return

        await b2b_service.update_license_branding(
            session, license_data["license_id"], field_path, value
        )

        await state.clear()
        await message.answer(
            f"✅ <b>Success!</b>\n\nField <code>{field_path}</code> updated to:\n{value}",
            reply_markup=b2b_menu_keyboard(has_active_license=True),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("b2b_branding_update_failed", error=str(e), user_id=message.from_user.id)  # type: ignore[union-attr]
        await message.answer(f"❌ <b>Update failed</b>\n\nReason: {e}", parse_mode="HTML")


@router.callback_query(F.data == "b2b:spawn")
async def cb_b2b_spawn(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show instructions for spawning a bot via Managed Bot API."""
    if not callback.message:
        return

    license_data = await b2b_service.get_active_license(session, callback.from_user.id)
    if not license_data:
        await callback.answer("❌ Active license required.", show_alert=True)
        return

    # Link: https://t.me/newbot?p2p_master_bot/suggested_name
    master_bot = settings.MASTER_BOT_USERNAME.replace("@", "")
    suggested_name = f"p2p_{callback.from_user.id}"
    spawn_link = f"https://t.me/newbot?{master_bot}/{suggested_name}"

    text = (
        "🚀 <b>Spawn Your Bot</b>\n\n"
        "We use Telegram's <b>Managed Bot API</b> for seamless deployment.\n\n"
        "1. Click the link below to open @BotFather\n"
        "2. Choose a name and username for your bot\n"
        "3. @BotFather will send a confirmation back to THIS bot\n\n"
        f"🔗 <a href='{spawn_link}'>Click here to Create Bot</a>\n\n"
        "<i>Note: Your License ID: <code>{license_data['license_id']}</code></i>"
    )
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    await callback.message.edit_text(
        text,
        reply_markup=b2b_menu_keyboard(has_active_license=True),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.message(F.managed_bot_created)
async def handle_managed_bot_created(
    message: Message,
    session: AsyncSession,
    bot_spawner: BotSpawnerService,
) -> None:
    """Handle service message from BotFather about a new managed bot."""
    if not message.managed_bot_created or not message.from_user:
        return

    bot_info = message.managed_bot_created
    log.info(
        "managed_bot_created_received",
        user_id=message.from_user.id,
        bot_id=bot_info.bot_id,  # type: ignore[attr-defined]
    )

    # 1. Find active license
    license_data = await b2b_service.get_active_license(session, message.from_user.id)
    if not license_data:
        await message.answer("❌ License not found. Please contact support.")
        return

    try:
        # 2. Get the token from BotFather using Managed Bot API
        token_data = await message.bot.get_managed_bot_token(bot_id=bot_info.bot_id)  # type: ignore[attr-defined, union-attr, call-arg]
        token = token_data.token  # type: ignore[union-attr]

        # 3. Update and spawn
        await bot_spawner.update_bot_token(session, license_data["license_id"], token)

        await message.answer(
            "✅ <b>Bot Successfully Spawned!</b>\n\n"
            f"Your bot @{bot_info.bot_username} is now online.\n"  # type: ignore[attr-defined]
            "Open it and send /start to begin.",
            reply_markup=b2b_menu_keyboard(has_active_license=True),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("managed_bot_spawn_failed", error=str(e), user_id=message.from_user.id)
        await message.answer("❌ Failed to retrieve bot token or start instance. Please try again.")
