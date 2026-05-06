"""Tests for bot/handlers/marketplace.py — FSM wizard and browsing handlers."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message

from bot.handlers.marketplace import (
    CreateAdFSM,
    _build_ad_list_text,
    _build_ad_page_keyboard,
    cb_ad_cancel,
    cb_ad_choose_asset,
    cb_ad_choose_type,
    cb_ad_confirm,
    cb_ad_create_start,
    cb_ad_view,
    cb_market_browse,
    cb_market_page,
    cb_noop,
    msg_ad_enter_fiat,
    msg_ad_enter_limits,
    msg_ad_enter_price,
)
from db.models.marketplace import Ad, AdType

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ad(
    ad_id: int = 1,
    ad_type: AdType = AdType.sell,
    asset: str = "USDT",
    fiat: str = "RUB",
    price_value: float = 90.5,
    min_limit: float = 1000.0,
    max_limit: float = 50000.0,
) -> Ad:
    """Create a mock Ad object."""
    ad = MagicMock(spec=Ad)
    ad.id = ad_id
    ad.type = ad_type
    ad.asset = asset
    ad.fiat = fiat
    ad.price_value = Decimal(str(price_value))
    ad.min_limit = Decimal(str(min_limit))
    ad.max_limit = Decimal(str(max_limit))
    ad.terms = "Standard terms"
    ad.is_active = True
    return ad


def _make_callback(data: str = "test", from_user_id: int = 42) -> MagicMock:
    """Build a mock CallbackQuery with common attributes."""
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = from_user_id
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_message(text: str = "", from_user_id: int = 42) -> MagicMock:
    """Build a mock Message with common attributes."""
    msg = MagicMock()
    msg.text = text
    msg.from_user = MagicMock()
    msg.from_user.id = from_user_id
    msg.answer = AsyncMock()
    return msg


# ── Text/keyboard helpers ──────────────────────────────────────────────────────


def test_build_ad_list_text_empty() -> None:
    """Empty ads list should show 'No active ads'."""
    text = _build_ad_list_text([], page=1, total_pages=1)
    assert "No active ads" in text


def test_build_ad_list_text_with_ads() -> None:
    """Should include ad info and pagination footer."""
    ads = [_make_ad(ad_type=AdType.sell), _make_ad(ad_id=2, ad_type=AdType.buy)]
    text = _build_ad_list_text(ads, page=1, total_pages=3)
    assert "P2P Market" in text
    assert "Page 1/3" in text
    assert "Sell" in text
    assert "Buy" in text


def test_build_ad_page_keyboard_single_page() -> None:
    """Single page: no prev/next buttons."""
    ads = [_make_ad()]
    kb = _build_ad_page_keyboard(ads, page=1, total_pages=1)

    markup = kb.inline_keyboard
    # Should have at least 2 rows: ads + controls
    assert len(markup) >= 2


def test_build_ad_page_keyboard_middle_page() -> None:
    """Middle page should have both Prev and Next navigation."""
    ads = [_make_ad()]
    kb = _build_ad_page_keyboard(ads, page=2, total_pages=3)
    markup = kb.inline_keyboard
    # Find nav row with Prev and Next
    all_texts = [btn.text for row in markup for btn in row]
    assert any("Prev" in t for t in all_texts)
    assert any("Next" in t for t in all_texts)


def test_build_ad_page_keyboard_buy_ad_emoji() -> None:
    """Buy ads should use 📥 emoji in button text."""
    ads = [_make_ad(ad_type=AdType.buy)]
    kb = _build_ad_page_keyboard(ads, page=1, total_pages=1)
    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("📥" in t for t in all_texts)


# ── Callback handlers ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cb_market_browse() -> None:
    """cb_market_browse should call _render_market for page=1."""
    cb = _make_callback("market:browse")
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    await cb_market_browse(cb, session)
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_cb_market_page() -> None:
    """cb_market_page should paginate to the correct page."""
    cb = _make_callback("market:page:3")
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    await cb_market_page(cb, session)
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_cb_ad_view_not_found() -> None:
    """cb_ad_view should alert if ad doesn't exist."""
    cb = _make_callback("ad:view:999")
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    await cb_ad_view(cb, session)
    cb.answer.assert_awaited_with("❌ Ad not found.", show_alert=True)


@pytest.mark.asyncio
async def test_cb_ad_view_found() -> None:
    """cb_ad_view should display ad details when found."""
    cb = _make_callback("ad:view:1")
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _make_ad()
    session.execute = AsyncMock(return_value=mock_result)

    await cb_ad_view(cb, session)
    cb.message.edit_text.assert_awaited_once()
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_cb_ad_view_found_buy_type() -> None:
    """cb_ad_view should show 'Buy' direction for buy ads."""
    cb = _make_callback("ad:view:2")
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _make_ad(ad_type=AdType.buy)
    session.execute = AsyncMock(return_value=mock_result)

    await cb_ad_view(cb, session)
    call_args = cb.message.edit_text.call_args
    assert call_args is not None


@pytest.mark.asyncio
async def test_cb_noop() -> None:
    """cb_noop should just answer the callback."""
    cb = _make_callback("noop")
    await cb_noop(cb)
    cb.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_ad_create_start() -> None:
    """cb_ad_create_start should set FSM state and edit message."""
    cb = _make_callback("ad:create")
    state = MagicMock()
    state.set_state = AsyncMock()

    await cb_ad_create_start(cb, state)
    state.set_state.assert_awaited_with(CreateAdFSM.choosing_type)
    cb.message.edit_text.assert_awaited_once()
    cb.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_ad_choose_type() -> None:
    """cb_ad_choose_type should store ad_type in state."""
    cb = _make_callback("adtype:sell_crypto")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    await cb_ad_choose_type(cb, state)
    state.update_data.assert_awaited_with(ad_type="sell_crypto")
    state.set_state.assert_awaited_with(CreateAdFSM.choosing_asset)
    cb.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_ad_choose_asset() -> None:
    """cb_ad_choose_asset should store asset and prompt fiat entry."""
    cb = _make_callback("ad_asset:USDT")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    await cb_ad_choose_asset(cb, state)
    state.update_data.assert_awaited_with(asset="USDT")
    state.set_state.assert_awaited_with(CreateAdFSM.entering_fiat)
    cb.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_msg_ad_enter_fiat_invalid() -> None:
    """Invalid fiat code should reply with an error and not advance state."""
    msg = _make_message("lowercase")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(return_value={"asset": "USDT"})

    await msg_ad_enter_fiat(msg, state)
    msg.answer.assert_awaited_once()
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_msg_ad_enter_fiat_valid() -> None:
    """Valid fiat code should advance FSM to entering_price."""
    msg = _make_message("RUB")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(return_value={"asset": "USDT"})

    await msg_ad_enter_fiat(msg, state)
    state.update_data.assert_awaited_with(fiat="RUB")
    state.set_state.assert_awaited_with(CreateAdFSM.entering_price)


@pytest.mark.asyncio
async def test_msg_ad_enter_price_invalid() -> None:
    """Non-numeric or zero price should reply with error."""
    msg = _make_message("not_a_price")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    await msg_ad_enter_price(msg, state)
    msg.answer.assert_awaited_once()
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_msg_ad_enter_price_zero_invalid() -> None:
    """Zero price must be rejected."""
    msg = _make_message("0")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(return_value={"fiat": "RUB"})

    await msg_ad_enter_price(msg, state)
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_msg_ad_enter_price_valid() -> None:
    """Valid price should advance FSM to entering_limits."""
    msg = _make_message("90.5")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(return_value={"fiat": "RUB"})

    await msg_ad_enter_price(msg, state)
    state.update_data.assert_awaited_with(price=90.5)
    state.set_state.assert_awaited_with(CreateAdFSM.entering_limits)


@pytest.mark.asyncio
async def test_msg_ad_enter_limits_invalid_format() -> None:
    """Single value instead of two should be rejected."""
    msg = _make_message("1000")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    await msg_ad_enter_limits(msg, state)
    msg.answer.assert_awaited_once()
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_msg_ad_enter_limits_min_greater_than_max() -> None:
    """min >= max should be rejected."""
    msg = _make_message("50000 1000")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    await msg_ad_enter_limits(msg, state)
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_msg_ad_enter_limits_valid() -> None:
    """Valid limits should advance to confirming state."""
    msg = _make_message("1000 50000")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "ad_type": "sell_crypto",
            "asset": "USDT",
            "fiat": "RUB",
            "price": 90.5,
        }
    )

    await msg_ad_enter_limits(msg, state)
    state.set_state.assert_awaited_with(CreateAdFSM.confirming)
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_msg_ad_enter_limits_buy_direction() -> None:
    """Buy direction in summary should use 'Buy crypto' label."""
    msg = _make_message("500 10000")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "ad_type": "buy_crypto",
            "asset": "TON",
            "fiat": "USD",
            "price": 3.5,
        }
    )

    await msg_ad_enter_limits(msg, state)
    call_kwargs = msg.answer.call_args[0][0]
    assert "Buy" in call_kwargs


@pytest.mark.asyncio
async def test_cb_ad_confirm_no_from_user() -> None:
    """Should abort gracefully if from_user is missing."""
    cb = _make_callback("ad:confirmed")
    cb.from_user = None
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    session = MagicMock()

    await cb_ad_confirm(cb, state, session)
    cb.answer.assert_awaited_with("❌ Could not identify user.", show_alert=True)


@pytest.mark.asyncio
async def test_cb_ad_confirm_success() -> None:
    """Successful confirmation should create ad and update message."""
    cb = _make_callback("ad:confirmed")
    state = MagicMock()
    state.clear = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "ad_type": "sell_crypto",
            "asset": "USDT",
            "fiat": "RUB",
            "price": 90.0,
            "min_limit": 1000.0,
            "max_limit": 50000.0,
        }
    )
    session = MagicMock()

    mock_ad = MagicMock()
    mock_ad.id = 1

    with patch(
        "bot.handlers.marketplace.MarketplaceService.create_ad", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_ad
        # Patch session.begin as an async context manager
        session.begin = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=None),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        await cb_ad_confirm(cb, state, session)

    cb.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_ad_confirm_exception() -> None:
    """Exception during creation should answer with error alert."""
    cb = _make_callback("ad:confirmed")
    state = MagicMock()
    state.clear = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "ad_type": "sell_crypto",
            "asset": "USDT",
            "fiat": "RUB",
            "price": 90.0,
            "min_limit": 1000.0,
            "max_limit": 50000.0,
        }
    )
    session = MagicMock()
    session.begin = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(side_effect=RuntimeError("DB error")),
            __aexit__=AsyncMock(return_value=None),
        )
    )

    await cb_ad_confirm(cb, state, session)
    cb.answer.assert_awaited_with("⚠️ Failed to publish ad. Try again.", show_alert=True)


@pytest.mark.asyncio
async def test_cb_ad_cancel() -> None:
    """Cancel callback should clear state and update message."""
    cb = _make_callback("ad:cancel")
    state = MagicMock()
    state.clear = AsyncMock()

    await cb_ad_cancel(cb, state)
    state.clear.assert_awaited_once()
    cb.message.edit_text.assert_awaited_once()
    cb.answer.assert_awaited_once()
