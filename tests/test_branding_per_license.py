import uuid
from unittest.mock import MagicMock, patch

import pytest

from bot.config import branding_ctx, get_branding, load_license_branding, set_branding


@pytest.mark.asyncio
async def test_get_branding_default():
    """Verify that get_branding returns defaults when no context is set."""
    branding_ctx.set(None)
    branding = get_branding()
    assert "bot" in branding
    assert "ui" in branding


@pytest.mark.asyncio
async def test_set_branding_context():
    """Verify that set_branding updates the context value."""
    mock_branding = {"bot": {"name": "Custom Bot"}}
    set_branding(mock_branding)
    assert get_branding() == mock_branding
    branding_ctx.set(None)


@pytest.mark.asyncio
async def test_load_license_branding_success(session):
    """Verify merging of DB branding with defaults."""
    license_id = str(uuid.uuid4())
    custom_branding = {"bot": {"name": "White-Label Exchange"}, "ui": {"primary_color": "#FF0000"}}

    mock_lic = MagicMock()
    mock_lic.branding = custom_branding

    # Mock default branding
    default_branding = {
        "bot": {"name": "Master P2P", "support_handle": "@master"},
        "ui": {"primary_color": "#0000FF", "trades_emoji": "📋"},
    }

    with (
        patch("bot.config.load_branding", return_value=default_branding),
        patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec,
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_lic
        mock_exec.return_value = mock_result

        merged = await load_license_branding(session, license_id)

        # Verify merged result
        assert merged["bot"]["name"] == "White-Label Exchange"
        assert merged["bot"]["support_handle"] == "@master"  # From default
        assert merged["ui"]["primary_color"] == "#FF0000"  # Overridden
        assert merged["ui"]["trades_emoji"] == "📋"  # From default
