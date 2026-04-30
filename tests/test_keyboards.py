"""Tests for keyboard builders."""

from __future__ import annotations

from bot import keyboards
from db.models.order import Order, OrderStatus, OrderType


def test_main_menu_keyboard():
    kb = keyboards.main_menu_keyboard()
    assert kb.inline_keyboard


def test_ad_type_keyboard():
    kb = keyboards.ad_type_keyboard()
    assert len(kb.inline_keyboard) >= 2


def test_asset_keyboard():
    kb = keyboards.asset_keyboard()
    assert kb.inline_keyboard


def test_payment_method_keyboard():
    kb = keyboards.payment_method_keyboard()
    assert kb.inline_keyboard


def test_order_book_keyboard():
    order = Order(id=1, status=OrderStatus.active.value, order_type=OrderType.sell_crypto.value, amount=10, asset="USDT", fiat_amount=100, fiat_currency="USD", payment_method="Cash")
    kb = keyboards.order_book_keyboard([order], 1, 1)
    assert kb.inline_keyboard


def test_wallet_chain_keyboard():
    kb = keyboards.wallet_chain_keyboard()
    assert len(kb.inline_keyboard) >= 2


def test_wallet_actions_keyboard():
    kb = keyboards.wallet_actions_keyboard()
    assert kb.inline_keyboard


def test_admin_dashboard_keyboard():
    kb = keyboards.admin_dashboard_keyboard()
    assert kb.inline_keyboard


def test_dispute_resolve_keyboard():
    kb = keyboards.dispute_resolve_keyboard("123")
    assert kb.inline_keyboard


def test_ad_confirm_keyboard():
    kb = keyboards.ad_confirm_keyboard()
    assert kb.inline_keyboard


def test_payment_keyboard():
    kb = keyboards.payment_keyboard("http://pay.url", "order-id")
    assert kb.inline_keyboard


def test_order_detail_keyboard():
    kb = keyboards.order_detail_keyboard("order-id")
    assert kb.inline_keyboard


def test_active_trade_maker_keyboard():
    kb = keyboards.active_trade_maker_keyboard("order-id")
    assert kb.inline_keyboard


def test_active_trade_taker_keyboard():
    kb = keyboards.active_trade_taker_keyboard("order-id")
    assert kb.inline_keyboard


def test_fiat_confirm_keyboard():
    kb = keyboards.fiat_confirm_keyboard("order-id")
    assert kb.inline_keyboard


def test_back_to_menu_keyboard():
    kb = keyboards.back_to_menu_keyboard()
    assert kb.inline_keyboard


def test_admin_disputes_keyboard():
    order = Order(id=1, asset="USDT")
    kb = keyboards.admin_disputes_keyboard([order])
    assert kb.inline_keyboard
    
    kb_empty = keyboards.admin_disputes_keyboard([])
    assert kb_empty.inline_keyboard


def test_admin_dispute_action_keyboard():
    kb = keyboards.admin_dispute_action_keyboard("order-id")
    assert kb.inline_keyboard
