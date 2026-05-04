from unittest.mock import mock_open, patch

import pytest

from bot.config import _reset_branding_cache, get_branding, load_branding
from bot.keyboards import main_menu_keyboard
from services.order_service import _get_platform_fees


def test_load_branding_success():
    """Test that branding.yaml is found and parsed correctly."""
    _reset_branding_cache()
    mock_yaml = """
bot:
  name: "Test Bot"
  welcome_message: "Welcome to {bot_name}, {first_name}!"
  support_handle: "@test_support"
  help_text: "Help at {support_handle}"
ui:
  create_ad_emoji: "➕"
fees:
  maker_percent: 1.5
  taker_percent: 0.5
  fixed_fee: 0.1
"""
    with (
        patch("builtins.open", mock_open(read_data=mock_yaml)),
        patch("pathlib.Path.exists", return_value=True),
    ):
        branding = load_branding()
        assert branding["bot"]["name"] == "Test Bot"
        assert branding["fees"]["maker_percent"] == 1.5


def test_load_branding_missing_file():
    """Test that RuntimeError is raised when branding.yaml is absent."""
    _reset_branding_cache()
    with (
        patch("pathlib.Path.exists", return_value=False),
        pytest.raises(RuntimeError, match="branding.yaml not found"),
    ):
        load_branding()


def test_load_branding_cached():
    """Test that second call returns the same object, no re-read."""
    _reset_branding_cache()
    mock_yaml = "bot: {name: 'First'}"
    with (
        patch("builtins.open", mock_open(read_data=mock_yaml)),
        patch("pathlib.Path.exists", return_value=True),
    ):
        branding1 = get_branding()

    # Change mock data but it shouldn't be read again
    mock_yaml2 = "bot: {name: 'Second'}"
    with (
        patch("builtins.open", mock_open(read_data=mock_yaml2)),
        patch("pathlib.Path.exists", return_value=True),
    ):
        branding2 = get_branding()

    assert branding1 is branding2
    assert branding2["bot"]["name"] == "First"


def test_get_branding_returns_dict():
    """Test that get_branding returns a dict with expected top-level keys."""
    _reset_branding_cache()
    # Use real file or mock
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("builtins.open", mock_open(read_data="bot: {name: 'X'}\nui: {}\nfees: {}")),
    ):
        branding = get_branding()
        assert isinstance(branding, dict)
        assert "bot" in branding
        assert "ui" in branding
        assert "fees" in branding


def test_welcome_message_interpolation():
    """Test that {bot_name} and {first_name} are replaced correctly."""
    _reset_branding_cache()
    mock_branding = {
        "bot": {"name": "SuperBot", "welcome_message": "Hello from {bot_name}, {first_name}!"}
    }
    with patch("bot.config.load_branding", return_value=mock_branding):
        from bot.config import get_branding

        b = get_branding()
        welcome = b["bot"]["welcome_message"].format(bot_name=b["bot"]["name"], first_name="Alice")
        assert welcome == "Hello from SuperBot, Alice!"


def test_help_text_interpolation():
    """Test that {support_handle} is replaced correctly."""
    _reset_branding_cache()
    mock_branding = {
        "bot": {"support_handle": "@super_support", "help_text": "Need help? Msg {support_handle}"}
    }
    with patch("bot.config.load_branding", return_value=mock_branding):
        b = get_branding()
        help_text = b["bot"]["help_text"].format(support_handle=b["bot"]["support_handle"])
        assert help_text == "Need help? Msg @super_support"


def test_fee_engine_maker():
    """Test that _get_platform_fees('sell_crypto') returns maker fee."""
    _reset_branding_cache()
    mock_branding = {"fees": {"maker_percent": 1.2, "taker_percent": 0.8, "fixed_fee": 0.5}}
    with patch("bot.config.load_branding", return_value=mock_branding):
        percent, fixed = _get_platform_fees("sell_crypto")
        assert percent == 1.2
        assert fixed == 0.5


def test_fee_engine_taker():
    """Test that _get_platform_fees('buy_crypto') returns taker fee."""
    _reset_branding_cache()
    mock_branding = {"fees": {"maker_percent": 1.2, "taker_percent": 0.8, "fixed_fee": 0.5}}
    with patch("bot.config.load_branding", return_value=mock_branding):
        percent, fixed = _get_platform_fees("buy_crypto")
        assert percent == 0.8
        assert fixed == 0.5


def test_fee_engine_defaults_to_zero():
    """Test that missing fees section returns (0.0, 0.0)."""
    _reset_branding_cache()
    mock_branding = {}
    with patch("bot.config.load_branding", return_value=mock_branding):
        percent, fixed = _get_platform_fees("sell_crypto")
        assert percent == 0.0
        assert fixed == 0.0


def test_keyboard_uses_branding_emoji():
    """Test that main_menu_keyboard() uses emoji from branding."""
    _reset_branding_cache()
    mock_branding = {"ui": {"create_ad_emoji": "💎", "market_emoji": "🏪"}}
    with patch("bot.config.load_branding", return_value=mock_branding):
        kb = main_menu_keyboard()
        # Find the button with "Create Ad" text
        found = False
        for row in kb.inline_keyboard:
            for button in row:
                if "Create Ad" in button.text:
                    assert "💎" in button.text
                    found = True
        assert found
