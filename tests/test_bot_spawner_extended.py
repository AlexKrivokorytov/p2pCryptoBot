"""Extended tests for bot_spawner."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.bot_spawner import BotSpawnerService


@pytest.mark.asyncio
async def test_bot_spawner_spawn_failure():
    loader = AsyncMock()
    loader.add_bot.side_effect = Exception("spawn fail")

    session = AsyncMock()
    lic = MagicMock()
    lic.id = "lic_id"
    lic.bot_token_encrypted = "enc_token"
    lic.owner_id = 123

    # Setup the result chain carefully
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_scalars.all.return_value = [lic]

    session.execute.return_value = mock_result

    session_maker = MagicMock()
    session_maker.return_value.__aenter__.return_value = session

    spawner = BotSpawnerService(session_maker, loader)

    with patch("services.bot_spawner.decrypt", return_value="token"):
        await spawner.spawn_all_active()
        loader.add_bot.assert_called_once()


@pytest.mark.asyncio
async def test_bot_spawner_stop_bot():
    loader = AsyncMock()
    spawner = BotSpawnerService(MagicMock(), loader)
    await spawner.stop_bot("lic_id")
    loader.remove_bot.assert_called_once_with("lic_id")
