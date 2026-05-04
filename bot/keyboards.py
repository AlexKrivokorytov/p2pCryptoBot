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
            f"{type_emoji} {float(order.amount):.4g} {order.asset} "
            f"→ {float(order.fiat_amount):.2f} {order.fiat_currency} "
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
    )
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
