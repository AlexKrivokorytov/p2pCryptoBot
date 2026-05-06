"""Tests for db/engine.py — coverage boost."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from db.engine import _build_engine


def test_build_engine_called() -> None:
    """_build_engine should use settings to create engine and factory."""
    mock_settings = MagicMock()
    mock_settings.POSTGRES_URI = "postgresql+asyncpg://user:pass@localhost/db"
    mock_settings.DB_POOL_SIZE = 5
    mock_settings.DB_MAX_OVERFLOW = 10

    with (
        patch("bot.config.get_settings", return_value=mock_settings),
        patch("db.engine.create_async_engine") as mock_create,
        patch("db.engine.async_sessionmaker") as mock_factory_cls,
    ):
        engine, factory = _build_engine()

        mock_create.assert_called_once_with(
            mock_settings.POSTGRES_URI,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        mock_factory_cls.assert_called_once()
        assert engine is mock_create.return_value
        assert factory is mock_factory_cls.return_value
