"""FSM state groups for all P2P bot user flows."""

from aiogram.fsm.state import State, StatesGroup


class CreateAdFSM(StatesGroup):
    """Flow: Maker creates a new P2P ad (order)."""

    choose_type = State()           # sell_crypto or buy_crypto
    choose_asset = State()          # BTC, USDT, TON, etc.
    enter_amount = State()          # crypto amount
    enter_fiat_currency = State()   # RUB, EUR, USD, etc.
    enter_fiat_amount = State()     # fiat price
    enter_payment_method = State()  # Sberbank, Revolut, etc.
    confirm = State()               # review and confirm


class BrowseOrderBookFSM(StatesGroup):
    """Flow: user browses the P2P Order Book."""

    choose_asset = State()
    browsing = State()              # paginating through active orders


class TakeOrderFSM(StatesGroup):
    """Flow: Taker confirms accepting a trade from the Order Book."""

    confirm_take = State()


class AwaitFiatConfirmationFSM(StatesGroup):
    """Flow: Maker confirms fiat payment received from Taker."""

    await_confirmation = State()


class DisputeFSM(StatesGroup):
    """Flow: maker or taker raises a dispute."""

    enter_reason = State()
    confirm_dispute = State()


class ArbitrationFSM(StatesGroup):
    """Flow: moderator resolves a dispute."""
    enter_order_id = State()
    choose_decision = State()


class TradeChatFSM(StatesGroup):
    """FSM for anonymous trade chat."""
    chatting = State()
