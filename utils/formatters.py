"""Message formatters — order summaries and error templates for the bot."""

from __future__ import annotations

from db.models.order import Order, OrderStatus

_STATUS_EMOJI: dict[str, str] = {
    OrderStatus.pending_funding: "🕐",
    OrderStatus.active: "📢",
    OrderStatus.escrow_held: "🔒",
    OrderStatus.completed: "✅",
    OrderStatus.dispute: "⚠️",
    OrderStatus.cancelled: "❌",
}


def format_order_summary(order: Order) -> str:
    """Return a human-readable Telegram message summarising the order.

    Args:
        order: The Order ORM instance.

    Returns:
        Markdown-formatted string safe for ``parse_mode="HTML"``.
    """
    emoji = _STATUS_EMOJI.get(order.status, "❓")
    type_label = "📤 Sell" if order.order_type == "sell_crypto" else "📥 Buy"
    return (
        f"{emoji} <b>Order #{str(order.id)[:8]}…</b>\n"
        f"Type: {type_label}\n"
        f"Asset: <code>{order.asset}</code>\n"
        f"Amount: <code>{float(order.amount):.8g}</code>\n"
        f"Fiat: <code>{float(order.fiat_amount):.2f} {order.fiat_currency}</code>\n"
        f"Payment: <b>{order.payment_method}</b>\n"
        f"Status: <b>{order.status}</b>\n"
        f"Fee: <code>{float(order.total_fee):.8g} {order.asset}</code>"
    )


def format_payment_instructions(order: Order) -> str:
    """Return payment instructions with the Crypto Pay link.

    Args:
        order: The Order ORM instance (must have ``payment_url`` set).

    Returns:
        Markdown-formatted instruction string.
    """
    url = order.payment_url or "N/A"
    return (
        f"💳 <b>Pay via Crypto Pay</b>\n\n"
        f"Amount: <code>{float(order.amount):.8g} {order.asset}</code>\n"
        f"Order ID: <code>{order.id}</code>\n\n"
        f"👇 Tap the button below to complete payment:\n"
        f'<a href="{url}">Pay Now</a>\n\n'
        f"⏱ Payment link expires in 30 minutes."
    )


def format_error(message: str) -> str:
    """Wrap an error message in a standard bot error template.

    Args:
        message: Human-readable error description.

    Returns:
        Formatted error string.
    """
    return f"❌ <b>Error:</b> {message}"


def format_dispute_raised(order_id: str, reason: str) -> str:
    """Return a dispute notification message.

    Args:
        order_id: UUID string of the order.
        reason: Dispute reason provided by the user.

    Returns:
        Formatted dispute notification string.
    """
    return (
        f"⚠️ <b>Dispute Raised</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n"
        f"Reason: {reason}\n\n"
        "A moderator will review this shortly."
    )
