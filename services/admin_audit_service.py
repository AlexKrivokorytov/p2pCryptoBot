"""Service for retrieving and formatting administrative audit logs."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.admin import AdminAuditLog


async def get_recent_logs(session: AsyncSession, limit: int = 10) -> list[AdminAuditLog]:
    """Fetch the most recent administrative audit logs."""
    stmt = select(AdminAuditLog).order_by(desc(AdminAuditLog.created_at)).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def format_log_entry(log: AdminAuditLog) -> str:
    """Format a single audit log entry for Telegram display."""
    # created_at might be None if not yet flushed/committed, though usually it's set
    ts = log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else "N/A"

    # Action labels
    action_icons = {
        "inject_balance": "💰",
        "activate_license_bypass": "💎",
        "force_order_status": "⚙️",
    }
    icon = action_icons.get(log.action, "📝")

    details_str = ""
    if log.details:
        # Simple key-value formatting for details
        details_str = " ".join([f"<i>{k}</i>:<code>{v}</code>" for k, v in log.details.items()])

    return (
        f"{icon} <b>{log.action}</b>\n"
        f"Admin: <code>{log.admin_id}</code> | Target: <code>{log.target_id or '—'}</code>\n"
        f"Time: <code>{ts}</code>\n"
        f"Details: {details_str}\n"
    )


def format_logs_message(logs: list[AdminAuditLog]) -> str:
    """Format a list of audit logs into a single Telegram message."""
    if not logs:
        return "📋 <b>Audit Logs</b>\n\nNo logs found."

    header = "📋 <b>Recent Admin Actions</b>\n\n"
    entries = [format_log_entry(entry) for entry in logs]
    return header + "\n".join(entries)
