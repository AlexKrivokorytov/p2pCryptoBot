"""Tests for bot/i18n.py — JsonDictCore and DatabaseManager."""

from __future__ import annotations

import json
import pathlib
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.i18n import DatabaseManager, JsonDictCore, setup_i18n


# ── JsonDictCore ───────────────────────────────────────────────────────────────


class TestJsonDictCore:
    """Tests for the custom JSON-based i18n core."""

    def _make_core(self) -> JsonDictCore:
        """Create a JsonDictCore with a real temporary locale directory."""
        return JsonDictCore(path="/tmp/{locale}")

    def test_get_returns_translated_string(self) -> None:
        """get() should resolve a dotted key to the correct string."""
        core = self._make_core()
        core._locales = {"en": {"greeting": "Hello, World!"}}  # type: ignore[attr-defined]
        core._default_locale = "en"  # type: ignore[attr-defined]

        # Patch get_locale and get_translator
        core.get_locale = MagicMock(return_value="en")  # type: ignore[method-assign]
        core.get_translator = MagicMock(return_value={"greeting": "Hello, World!"})  # type: ignore[method-assign]

        result = core.get("greeting", "en")
        assert result == "Hello, World!"

    def test_get_with_nested_key(self) -> None:
        """get() should navigate nested dict keys."""
        core = self._make_core()
        core.get_locale = MagicMock(return_value="en")  # type: ignore[method-assign]
        core.get_translator = MagicMock(  # type: ignore[method-assign]
            return_value={"menu": {"start": "Start trading"}}
        )

        result = core.get("menu.start", "en")
        assert result == "Start trading"

    def test_get_with_format_kwargs(self) -> None:
        """get() should format the string with provided keyword arguments."""
        core = self._make_core()
        core.get_locale = MagicMock(return_value="en")  # type: ignore[method-assign]
        core.get_translator = MagicMock(  # type: ignore[method-assign]
            return_value={"welcome": "Hello, {name}!"}
        )

        result = core.get("welcome", "en", name="Alex")
        assert result == "Hello, Alex!"

    def test_get_returns_key_if_not_found(self) -> None:
        """get() should return the original key if translation is missing."""
        core = self._make_core()
        core.get_locale = MagicMock(return_value="en")  # type: ignore[method-assign]
        core.get_translator = MagicMock(return_value={})  # type: ignore[method-assign]

        result = core.get("missing.key", "en")
        assert result == "missing.key"

    def test_get_returns_key_if_intermediate_not_dict(self) -> None:
        """get() should return key if intermediate value is not a dict."""
        core = self._make_core()
        core.get_locale = MagicMock(return_value="en")  # type: ignore[method-assign]
        core.get_translator = MagicMock(  # type: ignore[method-assign]
            return_value={"level": "just a string"}  # "level" is not a dict
        )

        result = core.get("level.deeper", "en")
        assert result == "level.deeper"

    def test_get_returns_key_if_format_key_error(self) -> None:
        """get() should return raw string if format fails due to missing kwarg."""
        core = self._make_core()
        core.get_locale = MagicMock(return_value="en")  # type: ignore[method-assign]
        core.get_translator = MagicMock(  # type: ignore[method-assign]
            return_value={"msg": "Hello, {name}!"}
        )

        result = core.get("msg", "en")  # no 'name' kwarg
        assert result == "Hello, {name}!"

    def test_get_returns_key_if_value_not_string(self) -> None:
        """get() should return key if resolved value is not a str."""
        core = self._make_core()
        core.get_locale = MagicMock(return_value="en")  # type: ignore[method-assign]
        core.get_translator = MagicMock(  # type: ignore[method-assign]
            return_value={"nested": {"more": {"even_more": 42}}}  # integer, not str
        )

        result = core.get("nested.more.even_more", "en")
        assert result == "nested.more.even_more"

    def test_find_locales_loads_json_files(self) -> None:
        """find_locales() should load and merge JSON files from locale dirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            locale_dir = pathlib.Path(tmpdir) / "en"
            locale_dir.mkdir()
            (locale_dir / "messages.json").write_text(
                json.dumps({"hello": "Hello"}), encoding="utf-8"
            )

            core = JsonDictCore(path=str(tmpdir) + "/{locale}")
            # Patch the internal methods that look at the filesystem
            core._extract_locales = MagicMock(return_value=["en"])  # type: ignore[attr-defined]
            core._find_locales = MagicMock(  # type: ignore[attr-defined]
                return_value={"en": [str(locale_dir / "messages.json")]}
            )

            result = core.find_locales()
            assert "en" in result
            assert result["en"]["hello"] == "Hello"


# ── DatabaseManager ────────────────────────────────────────────────────────────


class TestDatabaseManager:
    """Tests for the async locale manager."""

    @pytest.mark.asyncio
    async def test_get_locale_from_db_user(self) -> None:
        """Should return language_code from DB user if set."""
        manager = DatabaseManager()
        db_user = MagicMock()
        db_user.language_code = "ru"

        locale = await manager.get_locale(event_from_user=None, db_user=db_user)
        assert locale == "ru"

    @pytest.mark.asyncio
    async def test_get_locale_fallback_to_tg_user(self) -> None:
        """Should fallback to Telegram user language if DB user has no language_code."""
        manager = DatabaseManager()
        db_user = MagicMock()
        db_user.language_code = None

        tg_user = MagicMock()
        tg_user.language_code = "de"

        locale = await manager.get_locale(event_from_user=tg_user, db_user=db_user)
        assert locale == "de"

    @pytest.mark.asyncio
    async def test_get_locale_default_en(self) -> None:
        """Should return 'en' if no user info is available."""
        manager = DatabaseManager()
        locale = await manager.get_locale(event_from_user=None, db_user=None)
        assert locale == "en"

    @pytest.mark.asyncio
    async def test_set_locale_is_noop(self) -> None:
        """set_locale should do nothing and not raise."""
        manager = DatabaseManager()
        await manager.set_locale("ru", db_user=None)  # Must not raise


# ── setup_i18n ────────────────────────────────────────────────────────────────


class TestSetupI18n:
    """Integration test for setup_i18n factory."""

    def test_setup_i18n_returns_middleware(self) -> None:
        """setup_i18n should return an I18nMiddleware instance."""
        from aiogram_i18n import I18nMiddleware

        middleware = setup_i18n()
        assert isinstance(middleware, I18nMiddleware)
