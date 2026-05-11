"""Inline keyboards for the P2P bot."""

from __future__ import annotations

import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import get_branding
from db.models.order import Order, SupportedAsset

# ── Main menu ──────────────────────────────────────────────────────────────────


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the main menu keyboard."""
    b = get_branding()
    ui = b.get("ui", {})
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"{ui.get('create_ad_emoji', '📝')} Create Ad", callback_data="ad:create"
        ),
        InlineKeyboardButton(
            text=f"{ui.get('market_emoji', '🛒')} P2P Market", callback_data="market:browse"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=f"{ui.get('trades_emoji', '📋')} My Trades", callback_data="trades:my"
        ),
        InlineKeyboardButton(
            text=f"{ui.get('profile_emoji', '👤')} Profile", callback_data="menu:profile"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=f"{ui.get('wallet_emoji', '💼')} Wallets", callback_data="menu:wallet"
        ),
        InlineKeyboardButton(text="⚙️ Settings", callback_data="settings"),
    )
    builder.row(
        InlineKeyboardButton(text="❓ Help", callback_data="help"),
        InlineKeyboardButton(text="💎 B2B SaaS", callback_data="b2b:menu"),
    )
    return builder.as_markup()


# ── Ad type selection ──────────────────────────────────────────────────────────


def ad_type_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for choosing sell or buy crypto."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📤 Sell Crypto", callback_data="adtype:sell_crypto"),
        InlineKeyboardButton(text="📥 Buy Crypto", callback_data="adtype:buy_crypto"),
    )
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="ad:cancel"))
    return builder.as_markup()


# ── Asset selection ────────────────────────────────────────────────────────────


def asset_keyboard(prefix: str = "asset") -> InlineKeyboardMarkup:
    """Return inline keyboard for selecting a supported crypto asset.

    Args:
        prefix: Callback data prefix. Defaults to "asset".
    """
    builder = InlineKeyboardBuilder()
    for a in SupportedAsset:
        builder.button(text=a.value, callback_data=f"{prefix}:{a.value}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="ad:cancel"))
    return builder.as_markup()


# ── Payment method selection ───────────────────────────────────────────────────


def payment_method_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for choosing a fiat payment method."""
    b = get_branding()
    methods = b.get("payment_methods", [])
    builder = InlineKeyboardBuilder()
    for method in methods:
        builder.button(text=str(method), callback_data=f"paymethod:{method}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="ad:cancel"))
    return builder.as_markup()


# ── Ad confirmation ────────────────────────────────────────────────────────────


def ad_confirm_keyboard() -> InlineKeyboardMarkup:
    """Return confirm/cancel keyboard for ad review step."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Confirm & Pay", callback_data="ad:confirmed"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="ad:cancel"),
    )
    return builder.as_markup()


# ── Payment link ───────────────────────────────────────────────────────────────


def payment_keyboard(pay_url: str, order_id: str) -> InlineKeyboardMarkup:
    """Return the pay-now + check-status keyboard.

    Args:
        pay_url: Crypto Pay payment URL.
        order_id: UUID string of the order.
    """
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Pay Now", url=pay_url))
    builder.row(
        InlineKeyboardButton(text="🔄 Check Status", callback_data=f"order:status:{order_id}"),
        InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"order:cancel:{order_id}"),
    )
    return builder.as_markup()


# ── Order Book ─────────────────────────────────────────────────────────────────


def order_book_keyboard(
    orders: list[Order],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Return paginated Order Book keyboard.

    Args:
        orders: List of active Order objects for the current page.
        page: Current page number (1-indexed).
        total_pages: Total number of pages.
    """
    builder = InlineKeyboardBuilder()

    for order in orders:
        b = get_branding()
        ui = b.get("ui", {})
        sell_emoji = ui.get("sell_emoji", "📤")
        buy_emoji = ui.get("buy_emoji", "📥")
        type_emoji = sell_emoji if order.order_type == "sell_crypto" else buy_emoji
        label = (
            f"{type_emoji} {order.amount:.4g} {order.asset} "
            f"→ {order.fiat_amount:.2f} {order.fiat_currency} "
            f"({order.payment_method})"
        )
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"order:view:{order.id}",
            )
        )

    # Pagination
    nav_buttons: list[InlineKeyboardButton] = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Prev", callback_data=f"market:page:{page - 1}")
        )
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="➡️ Next", callback_data=f"market:page:{page + 1}")
        )
    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="🏠 Back to menu", callback_data="menu:main"))
    return builder.as_markup()


# ── Order detail (for Taker) ───────────────────────────────────────────────────


def order_detail_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Return detail view keyboard with Accept Trade button.

    Args:
        order_id: UUID string of the order.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Accept Trade", callback_data=f"trade:take:{order_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Back to Market", callback_data="market:browse"))
    return builder.as_markup()


# ── Active trade keyboards ─────────────────────────────────────────────────────


def active_trade_maker_keyboard(order_id: str | uuid.UUID) -> InlineKeyboardMarkup:
    """Keyboard for the Maker during an active trade."""
    if isinstance(order_id, uuid.UUID):
        order_id = str(order_id)

    b = get_branding()
    ui = b.get("ui", {})
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💬 Chat with Taker", callback_data=f"chat:enter:{order_id}"),
        InlineKeyboardButton(
            text=f"{ui.get('dispute_emoji', '⚖️')} Dispute",
            callback_data=f"dispute:raise:{order_id}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=f"{ui.get('escrow_emoji', '🔒')} Release Escrow",
            callback_data=f"escrow:confirm:{order_id}",
        )
    )
    return builder.as_markup()


def active_trade_taker_keyboard(order_id: str | uuid.UUID) -> InlineKeyboardMarkup:
    """Keyboard for the Taker during an active trade."""
    if isinstance(order_id, uuid.UUID):
        order_id = str(order_id)

    b = get_branding()
    ui = b.get("ui", {})
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💸 I've sent fiat", callback_data=f"trade:fiat_sent:{order_id}")
    )
    builder.row(
        InlineKeyboardButton(text="💬 Chat with Maker", callback_data=f"chat:enter:{order_id}"),
        InlineKeyboardButton(
            text=f"{ui.get('dispute_emoji', '⚖️')} Dispute",
            callback_data=f"dispute:raise:{order_id}",
        ),
    )
    return builder.as_markup()


# ── Fiat confirmation (legacy compatibility) ───────────────────────────────────


def fiat_confirm_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Return keyboard for Maker to confirm fiat receipt.

    Args:
        order_id: UUID string of the order.
    """
    return active_trade_maker_keyboard(order_id)


# ── Dispute resolution (moderator) ─────────────────────────────────────────────


def dispute_resolve_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Return moderator decision keyboard for dispute resolution.

    Args:
        order_id: UUID string of the disputed order.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🟢 Taker wins",
            callback_data=f"dispute:resolve:{order_id}:taker_wins",
        ),
        InlineKeyboardButton(
            text="🔵 Maker wins",
            callback_data=f"dispute:resolve:{order_id}:maker_wins",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬛ Cancel (refund maker)",
            callback_data=f"dispute:resolve:{order_id}:cancel",
        )
    )
    return builder.as_markup()


# ── Generic back button ────────────────────────────────────────────────────────


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Return a single 'Back to menu' button."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Back to menu", callback_data="menu:main")
    return builder.as_markup()


# ── Wallet keyboards ────────────────────────────────────────────────────────────

# Mapping of chain key to display label — update here when adding new chains
WALLET_CHAIN_LABELS: dict[str, str] = {
    "ton": "🔷 TON",
    "evm": "🟡 EVM (BSC/ETH)",
}


def wallet_chain_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting a blockchain network to generate a wallet on."""
    builder = InlineKeyboardBuilder()
    for chain, label in WALLET_CHAIN_LABELS.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"wallet:generate:{chain}"))
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="menu:main"))
    return builder.as_markup()


def wallet_actions_keyboard() -> InlineKeyboardMarkup:
    """Main wallet dashboard keyboard — shown after wallet list or generation.

    Buttons:
    - 💰 Check Balance — fetch live on-chain balances
    - ➕ Add Wallet — choose chain for new wallet generation
    - 🏠 Back to menu
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 Check Balance", callback_data="wallet:balance"),
    )
    builder.row(
        InlineKeyboardButton(text="➕ Add Wallet", callback_data="wallet:add"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Back to menu", callback_data="menu:main"))
    return builder.as_markup()


# ── Admin Dashboard keyboards ──────────────────────────────────────────────────


def admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Main admin panel navigation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Stats", callback_data="admin:stats"),
        InlineKeyboardButton(text="⚖️ Disputes", callback_data="admin:disputes"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Refresh Stats", callback_data="admin:stats:refresh"),
        InlineKeyboardButton(text="📋 Audit Logs", callback_data="admin:audit"),
    )
    builder.row(
        InlineKeyboardButton(text="🛠️ Sandbox", callback_data="admin:sandbox:menu"),
        InlineKeyboardButton(text="🔍 Search User", callback_data="admin:user:search"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Menu", callback_data="menu:main"),
    )
    return builder.as_markup()


def admin_user_manage_keyboard(user_id: int, is_verified: bool) -> InlineKeyboardMarkup:
    """Keyboard for managing a specific user (verify/unverify)."""
    builder = InlineKeyboardBuilder()
    verify_text = "❌ Unverify" if is_verified else "✅ Verify"
    verify_data = f"admin:user:verify:{user_id}:{'0' if is_verified else '1'}"

    builder.row(InlineKeyboardButton(text=verify_text, callback_data=verify_data))
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin:stats"))
    return builder.as_markup()


def admin_sandbox_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the Admin Sandbox (Debug) menu."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💎 Activate License", callback_data="admin:sandbox:lic_bypass"),
        InlineKeyboardButton(text="💰 Add Test USDT", callback_data="admin:sandbox:add_usdt"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Order States", callback_data="admin:sandbox:order_state"),
        InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin:stats"),
    )
    return builder.as_markup()


def admin_sandbox_order_status_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Keyboard for selecting a target status to force on an order."""
    from db.models.order import OrderStatus

    builder = InlineKeyboardBuilder()

    # Common test statuses
    statuses = [
        OrderStatus.escrow_held,
        OrderStatus.completed,
        OrderStatus.cancelled,
        OrderStatus.dispute,
    ]

    for s in statuses:
        builder.button(
            text=s.value.upper(), callback_data=f"admin:sandbox:force:{order_id}:{s.value}"
        )

    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:sandbox:menu"))
    return builder.as_markup()


def admin_disputes_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    """Dispute queue keyboard — one button per disputed order."""
    builder = InlineKeyboardBuilder()
    for i, order in enumerate(orders, start=1):
        short_id = str(order.id)[:8]
        builder.row(
            InlineKeyboardButton(
                text=f"#{i} {short_id}… {order.asset}",
                callback_data=f"admin:dispute:view:{order.id}",
            )
        )
    if not orders:
        builder.row(InlineKeyboardButton(text="✅ No disputes!", callback_data="admin:stats"))
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def admin_dispute_action_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Per-dispute action keyboard shown when viewing a single dispute."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Taker wins",
            callback_data=f"dispute:resolve:{order_id}:taker_wins",
        ),
        InlineKeyboardButton(
            text="↩️ Maker wins",
            callback_data=f"dispute:resolve:{order_id}:maker_wins",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Cancel order",
            callback_data=f"dispute:resolve:{order_id}:cancel",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Back to disputes", callback_data="admin:disputes"),
    )
    return builder.as_markup()


# ── B2B / White-Label SaaS ────────────────────────────────────────────────────


def b2b_menu_keyboard(has_active_license: bool = False) -> InlineKeyboardMarkup:
    """Return keyboard for B2B SaaS menu."""
    builder = InlineKeyboardBuilder()
    if has_active_license:
        builder.row(InlineKeyboardButton(text="🚀 Spawn My Bot", callback_data="b2b:spawn"))
        builder.row(
            InlineKeyboardButton(text="🎨 Customize Branding", callback_data="b2b:customize")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="💎 Buy White-Label License", callback_data="b2b:buy")
        )

    builder.row(InlineKeyboardButton(text="🏠 Back to menu", callback_data="menu:main"))
    return builder.as_markup()


def b2b_purchase_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for purchasing B2B license."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ Pay with Stars (XTR)", callback_data="b2b:pay:stars"))
    builder.row(
        InlineKeyboardButton(text="🔷 Pay with TON (Coming Soon)", callback_data="b2b:pay:ton")
    )
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="b2b:menu"))
    return builder.as_markup()
