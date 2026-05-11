"""I18n setup for aiogram-i18n."""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING, Any

from aiogram.types import User as TgUser
from aiogram_i18n import I18nMiddleware
from aiogram_i18n.cores.base import BaseCore
from aiogram_i18n.managers.base import BaseManager

from db.models.user import User

if TYPE_CHECKING:

    class JsonDictCore(Any):
        """Custom JSON core for aiogram-i18n v1.5."""

        def get(self, message: str, locale: str | None = None, /, **kwargs: Any) -> str: ...

        def find_locales(self) -> dict[str, dict[str, Any]]: ...

    class DatabaseManager(Any):
        """Custom manager to extract language code from the DB User model."""

        async def get_locale(
            self,
            event_from_user: TgUser | None = None,
            db_user: User | None = None,
        ) -> str: ...

        async def set_locale(self, locale: str, db_user: User | None = None) -> None: ...

else:

    class JsonDictCore(BaseCore):
        """Custom JSON core for aiogram-i18n v1.5."""

        def get(self, message: str, locale: str | None = None, /, **kwargs: Any) -> str:
            """Get translated message by dotted key, formatted with kwargs."""
            locale = self.get_locale(locale)
            translator = self.get_translator(locale)

            keys = message.split(".")
            val: Any = translator
            for k in keys:
                if isinstance(val, dict):
                    val = val.get(k, message)
                else:
                    return message

            if isinstance(val, str):
                try:
                    return val.format(**kwargs)
                except KeyError:
                    return val
            return message

        def find_locales(self) -> dict[str, dict[str, Any]]:
            """Find and load all JSON locales."""
            locales = self._extract_locales(self.path)
            paths = self._find_locales(self.path, locales, ext=".json")

            translations: dict[str, dict[str, Any]] = {}
            for locale, files in paths.items():
                translations[locale] = {}
                for file in files:
                    with open(file, encoding="utf-8") as f:
                        data = json.load(f)
                        translations[locale].update(data)
            return translations

    class DatabaseManager(BaseManager):
        """Custom manager to extract language code from the DB User model."""

        async def get_locale(
            self,
            event_from_user: TgUser | None = None,
            db_user: User | None = None,
        ) -> str:
            """Get locale from the database user model injected by DbSessionMiddleware."""
            if db_user is not None and getattr(db_user, "language_code", None):
                return db_user.language_code

            # Fallback to telegram user language
            if event_from_user is not None and getattr(event_from_user, "language_code", None):
                return event_from_user.language_code or "en"

            return "en"

        async def set_locale(self, locale: str, db_user: User | None = None) -> None:
            """Set locale (not strictly needed here as we update the DB model in handlers)."""
            pass


def setup_i18n() -> I18nMiddleware:
    """Initialize I18nMiddleware with custom JSON core and Database manager."""
    locales_dir = pathlib.Path(__file__).parent.parent / "locales"

    # Initialize the core
    core = JsonDictCore(path=str(locales_dir) + "/{locale}")

    # Initialize I18nMiddleware
    i18n_middleware = I18nMiddleware(
        core=core,
        manager=DatabaseManager(),
        default_locale="en",
    )

    return i18n_middleware
