"""License validation guard for white-label distribution.

This module verifies that a buyer's LICENSE_KEY is mathematically
bound to their specific BOT_TOKEN before the bot is allowed to start.

HOW IT WORKS (for the seller — you):
    1. A buyer purchases the product and gives you their BOT_TOKEN.
    2. You call ``generate_license_key(bot_token)`` to produce a LICENSE_KEY.
    3. You send the LICENSE_KEY to the buyer.
    4. The buyer places it in their .env file as LICENSE_KEY=<value>.
    5. On every startup, the bot calls ``validate_license()`` which
       verifies the key. If it fails, the bot refuses to start.

SECURITY PROPERTIES:
    - HMAC-SHA256 with a private SELLER_SECRET known only to you.
    - Keys are bot-token specific — cannot be reused for a different bot.
    - Constant-time comparison prevents timing attacks.
    - Changing the bot token invalidates the license automatically.

SELLER INSTRUCTIONS:
    Set SELLER_SECRET as an environment variable on YOUR machine only.
    Never share this secret. Losing it means you cannot generate new keys.
    Generate it once with:
        python -c "import secrets; print(secrets.token_hex(32))"
"""

from __future__ import annotations

import hashlib
import hmac
import os

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_SELLER_SECRET_ENV = "SELLER_SECRET"
_LICENSE_KEY_ENV = "LICENSE_KEY"


def _get_seller_secret() -> bytes:
    """Return the seller's private HMAC secret from environment.

    Args:
        None

    Returns:
        The raw bytes of the SELLER_SECRET env var.

    Raises:
        RuntimeError: If SELLER_SECRET is not set in the environment.
    """
    secret = os.environ.get(_SELLER_SECRET_ENV, "").strip()
    if not secret:
        raise RuntimeError(
            "SELLER_SECRET environment variable is not set. "
            "This is required to validate license keys. "
            "Set it on your server and never share it."
        )
    return secret.encode()


def generate_license_key(bot_token: str) -> str:
    """Generate a LICENSE_KEY bound to a specific Telegram bot token.

    Run this on YOUR machine for each buyer before shipping the product.
    The buyer receives the output and places it in their .env file.

    Args:
        bot_token: The buyer's Telegram bot token (from @BotFather).

    Returns:
        A 64-character hex HMAC-SHA256 string to send to the buyer.

    Example::

        $ SELLER_SECRET=your_secret python -c "
        from utils.license_guard import generate_license_key
        print(generate_license_key('1234567890:ABCDEFabcdef'))
        "
    """
    secret = _get_seller_secret()
    mac = hmac.new(secret, bot_token.encode(), hashlib.sha256)
    return mac.hexdigest()


def validate_license(bot_token: str, license_key: str) -> bool:
    """Validate that a LICENSE_KEY is correct for the given BOT_TOKEN.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        bot_token: The BOT_TOKEN from the buyer's .env file.
        license_key: The LICENSE_KEY from the buyer's .env file.

    Returns:
        True if the license is valid, False otherwise.
    """
    expected = generate_license_key(bot_token)
    return hmac.compare_digest(expected, license_key.strip())


def check_license_or_abort(bot_token: str) -> None:
    """Check the license on startup and raise if invalid.

    Reads LICENSE_KEY from the environment and validates it against
    the provided BOT_TOKEN. If SELLER_SECRET is not set (development
    mode without license enforcement), validation is skipped with a
    WARNING log so the developer environment still works.

    Args:
        bot_token: The BOT_TOKEN currently in use.

    Raises:
        SystemExit: If LICENSE_KEY is present but invalid.
        RuntimeError: If LICENSE_KEY is missing in production mode
            (when SELLER_SECRET is set).
    """
    seller_secret = os.environ.get(_SELLER_SECRET_ENV, "").strip()

    # Development mode — SELLER_SECRET not configured, skip enforcement.
    if not seller_secret:
        log.warning(
            "license_check_skipped",
            reason=(
                "SELLER_SECRET not set — running in development mode without license enforcement"
            ),
        )
        return

    license_key = os.environ.get(_LICENSE_KEY_ENV, "").strip()
    if not license_key:
        log.error(
            "license_missing",
            message="LICENSE_KEY is not set in .env. Contact your vendor for a valid license key.",
        )
        raise SystemExit(1)

    if not validate_license(bot_token, license_key):
        log.error(
            "license_invalid",
            message=(
                "LICENSE_KEY does not match this BOT_TOKEN. "
                "Your license is bound to a different bot. "
                "Contact your vendor if you believe this is an error."
            ),
        )
        raise SystemExit(1)

    log.info("license_valid", status="ok")
