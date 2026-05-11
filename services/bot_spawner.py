"""Service for spawning and managing managed white-label bots."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.dynamic_loader import DynamicBotLoader
from db.models.b2b import B2BLicense
from utils.encryption import decrypt, encrypt

log = structlog.get_logger(__name__)


class BotSpawnerService:
    """Service to bridge DB licenses and the DynamicBotLoader."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        loader: DynamicBotLoader,
    ):
        self.session_maker = session_maker
        self.loader = loader

    async def spawn_all_active(self) -> None:
        """Fetch all active licenses with tokens and spawn bots."""
        async with self.session_maker() as session:
            stmt = select(B2BLicense).where(
                B2BLicense.is_active, B2BLicense.bot_token_encrypted.isnot(None)
            )
            result = await session.execute(stmt)
            licenses = result.scalars().all()

            for lic in licenses:
                try:
                    token = decrypt(lic.bot_token_encrypted)
                    await self.loader.add_bot(str(lic.id), token)
                    log.info("bot_spawned_startup", license_id=str(lic.id), owner_id=lic.owner_id)
                except Exception as e:
                    log.error("bot_spawn_failed", license_id=str(lic.id), error=str(e))

    async def update_bot_token(self, session: AsyncSession, license_id: str, token: str) -> None:
        """Update bot token in DB and respawn the bot."""
        # 1. Encrypt and save
        encrypted = encrypt(token)

        import uuid

        from sqlalchemy import update

        stmt = (
            update(B2BLicense)
            .where(B2BLicense.id == uuid.UUID(license_id))
            .values(bot_token_encrypted=encrypted)
        )
        await session.execute(stmt)
        await session.commit()

        # 2. Respawn in loader
        await self.loader.add_bot(license_id, token)
        log.info("bot_token_updated_and_respawned", license_id=license_id)

    async def stop_bot(self, license_id: str) -> None:
        """Stop a specific bot."""
        await self.loader.remove_bot(license_id)
        log.info("bot_manually_stopped", license_id=license_id)
