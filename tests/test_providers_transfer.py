from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from providers.wallet_provider import EvmWalletProvider, TonWalletProvider


@pytest.mark.asyncio
async def test_evm_transfer_native_success():
    """Test successful native EVM transfer (e.g. BNB)."""
    provider = EvmWalletProvider(rpc_url="http://mock-rpc")
    private_key = "0" * 64
    to_address = "0x" + "1" * 40
    amount = Decimal("1.5")

    mock_w3 = MagicMock()
    mock_w3.eth.get_transaction_count = AsyncMock(return_value=5)
    type(mock_w3.eth).chain_id = PropertyMock(return_value=AsyncMock(return_value=56)())
    mock_w3.eth.fee_history = AsyncMock(return_value={"baseFeePerGas": [1000000000]})
    mock_w3.eth.estimate_gas = AsyncMock(return_value=21000)
    mock_w3.eth.send_raw_transaction = AsyncMock(return_value=MagicMock(hex=lambda: "0x123"))
    mock_w3.to_wei.side_effect = lambda val, unit: (
        int(Decimal(str(val)) * Decimal("1e18"))
        if unit == "ether"
        else int(Decimal(str(val)) * Decimal("1e9"))
    )
    type(mock_w3.eth).gas_price = PropertyMock(return_value=AsyncMock(return_value=1000000000)())

    # Patch AsyncWeb3 inside the provider module to avoid breaking isinstance in the library
    with (
        patch("providers.wallet_provider.AsyncWeb3", return_value=mock_w3),
        patch("providers.wallet_provider.Account.from_key") as mock_from_key,
    ):
        mock_acct = MagicMock()
        mock_from_key.return_value = mock_acct
        mock_acct.address = "0x" + "2" * 40
        mock_acct.sign_transaction = MagicMock(return_value=MagicMock(raw_transaction=b"signed"))

        tx_hash = await provider.transfer(private_key, to_address, "BNB", amount)

        assert tx_hash == "0x123"


@pytest.mark.asyncio
async def test_evm_transfer_erc20_success():
    """Test successful ERC-20 transfer (e.g. USDT)."""
    provider = EvmWalletProvider(rpc_url="http://mock-rpc")
    private_key = "0" * 64
    to_address = "0x" + "1" * 40
    amount = Decimal("100")

    mock_w3 = MagicMock()
    mock_w3.eth.get_transaction_count = AsyncMock(return_value=10)
    type(mock_w3.eth).chain_id = PropertyMock(return_value=AsyncMock(return_value=56)())
    mock_w3.eth.fee_history = AsyncMock(return_value={"baseFeePerGas": [1000000000]})
    mock_w3.eth.estimate_gas = AsyncMock(return_value=50000)
    mock_w3.eth.send_raw_transaction = AsyncMock(return_value=MagicMock(hex=lambda: "0x456"))
    mock_w3.to_wei.side_effect = lambda val, unit: int(Decimal(str(val)) * Decimal("1e9"))
    type(mock_w3.eth).gas_price = PropertyMock(return_value=AsyncMock(return_value=1000000000)())

    mock_contract = MagicMock()
    mock_contract.functions.transfer.return_value.estimate_gas = AsyncMock(return_value=50000)
    mock_contract.functions.transfer.return_value._encode_transaction_data = MagicMock(
        return_value=b"data"
    )
    mock_w3.eth.contract.return_value = mock_contract

    with (
        patch("providers.wallet_provider.AsyncWeb3", return_value=mock_w3),
        patch("providers.wallet_provider.Account.from_key") as mock_from_key,
    ):
        mock_acct = MagicMock()
        mock_from_key.return_value = mock_acct
        mock_acct.address = "0x" + "2" * 40
        mock_acct.sign_transaction = MagicMock(return_value=MagicMock(raw_transaction=b"signed"))

        tx_hash = await provider.transfer(private_key, to_address, "USDT", amount)

        assert tx_hash == "0x456"


@pytest.mark.asyncio
async def test_ton_transfer_success():
    """Test successful TON transfer."""
    provider = TonWalletProvider(endpoint="http://mock-toncenter")
    private_key = "0" * 64
    to_address = "UQ" + "1" * 46
    amount = Decimal("2.5")

    mock_wallet = MagicMock()
    mock_wallet.address.to_str.return_value = "UQ_SENDER"

    mock_query = MagicMock()
    mock_query.message.to_boc.return_value.hex.return_value = "aabbcc"
    mock_query.message.hash.hex.return_value = "txhash"
    mock_wallet.create_transfer_message.return_value = mock_query

    mock_resp_seqno = AsyncMock()
    mock_resp_seqno.status = 200
    mock_resp_seqno.json.return_value = {"ok": True, "result": {"stack": [["num", "0x5"]]}}
    mock_resp_seqno.__aenter__.return_value = mock_resp_seqno

    mock_resp_send = AsyncMock()
    mock_resp_send.status = 200
    mock_resp_send.json.return_value = {"ok": True}
    mock_resp_send.__aenter__.return_value = mock_resp_send

    with (
        patch("pytoniq.WalletV4R2.from_private_key", new_callable=MagicMock) as mock_from_key,
        patch("aiohttp.ClientSession.post") as mock_post,
    ):
        mock_from_key.return_value = mock_wallet
        mock_post.side_effect = [mock_resp_seqno, mock_resp_send]

        tx_hash = await provider.transfer(private_key, to_address, "TON", amount)

        assert tx_hash == "txhash"


@pytest.mark.asyncio
async def test_ton_transfer_failure_insufficient_funds():
    """Test TON transfer failure (Toncenter error)."""
    provider = TonWalletProvider(endpoint="http://mock-toncenter")
    private_key = "0" * 64

    mock_wallet = MagicMock()
    mock_wallet.address.to_str.return_value = "UQ_SENDER"

    mock_resp_seqno = AsyncMock()
    mock_resp_seqno.status = 200
    mock_resp_seqno.json.return_value = {"ok": True, "result": {"stack": [["num", "0x5"]]}}
    mock_resp_seqno.__aenter__.return_value = mock_resp_seqno

    mock_resp_send = AsyncMock()
    mock_resp_send.status = 200
    mock_resp_send.json.return_value = {"ok": False, "error": "Insufficient funds"}
    mock_resp_send.__aenter__.return_value = mock_resp_send

    with (
        patch("pytoniq.WalletV4R2.from_private_key", new_callable=MagicMock) as mock_from_key,
        patch("aiohttp.ClientSession.post") as mock_post,
    ):
        mock_from_key.return_value = mock_wallet
        mock_post.side_effect = [mock_resp_seqno, mock_resp_send]

        with pytest.raises(RuntimeError, match="Toncenter error: Insufficient funds"):
            await provider.transfer(private_key, "to", "TON", Decimal("1"))
