"""B2B Phase 5 tests — Managed white-label bot spawning."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.dynamic_loader import DynamicBotLoader
from db.models.b2b import B2BLicense
from services.bot_spawner import BotSpawnerService

pytestmark = pytest.mark.b2b


@pytest.mark.asyncio
async def test_dynamic_loader_add_remove():
    session_pool = MagicMock(spec=async_sessionmaker)
    crypto_pay = MagicMock()
    loader = DynamicBotLoader(session_pool, crypto_pay, [])

    license_id = str(uuid.uuid4())
    token = "12345:ABCDE"

    with patch("bot.dynamic_loader.Bot", spec=Bot) as mock_bot_class:
        mock_bot = mock_bot_class.return_value
        mock_bot.id = 123

        # Test add
        await loader.add_bot(license_id, token)
        assert license_id in loader.instances
        assert loader.instances[license_id].bot == mock_bot

        # Test remove
        await loader.remove_bot(license_id)
        assert license_id not in loader.instances


@pytest.mark.asyncio
async def test_bot_spawner_spawn_all_active(session: AsyncSession):
    # Create user first
    from services.user_service import get_or_create_user

    await get_or_create_user(session, telegram_id=123, username="testowner")
    await session.commit()

    # Setup active license with token
    from utils.encryption import encrypt

    token = "999:TOKEN"

    # We need a license ID (UUID)
    license_uuid = uuid.uuid4()

    lic = B2BLicense(
        id=license_uuid,
        owner_id=123,
        expires_at=datetime.utcnow(),
        bot_token_encrypted=encrypt(token),
        is_active=True,
        branding={},
    )
    session.add(lic)
    await session.commit()

    loader = AsyncMock(spec=DynamicBotLoader)

    # Mock the session maker to work as a context manager returning our session
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_maker = MagicMock()
    session_maker.return_value = session_context

    spawner = BotSpawnerService(session_maker, loader)

    await spawner.spawn_all_active()

    loader.add_bot.assert_called_once()
    args = loader.add_bot.call_args[0]
    assert args[1] == token


@pytest.mark.asyncio
async def test_bot_spawner_update_token(session: AsyncSession):
    # Create user first
    from services.user_service import get_or_create_user

    await get_or_create_user(session, telegram_id=456, username="testop")
    await session.commit()

    lic = B2BLicense(owner_id=456, expires_at=datetime.utcnow(), is_active=True, branding={})
    session.add(lic)
    await session.commit()
    license_id = str(lic.id)

    loader = AsyncMock(spec=DynamicBotLoader)
    spawner = BotSpawnerService(None, loader)

    new_token = "new:token"
    await spawner.update_bot_token(session, license_id, new_token)

    # Verify DB updated
    await session.refresh(lic)
    from utils.encryption import decrypt

    assert decrypt(lic.bot_token_encrypted) == new_token

    # Verify loader called
    loader.add_bot.assert_called_once_with(license_id, new_token)
