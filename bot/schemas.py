"""Strict schemas for B2B branding and UI customisation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BotBrandingSchema(BaseModel):
    """Schema for bot identity and messages."""

    name: str | None = Field(None, min_length=1, max_length=64)
    welcome_message: str | None = Field(None, min_length=10, max_length=2048)
    help_text: str | None = Field(None, min_length=10, max_length=2048)
    support_handle: str | None = Field(None, pattern=r"^@[\w\d_]+$")


class UIBrandingSchema(BaseModel):
    """Schema for UI elements like emojis and colors."""

    primary_color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    trades_emoji: str | None = Field(None, min_length=1, max_length=4)
    wallet_emoji: str | None = Field(None, min_length=1, max_length=4)


class BrandingSchema(BaseModel):
    """Root schema for per-license branding overrides."""

    bot: BotBrandingSchema | None = None
    ui: UIBrandingSchema | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrandingSchema:
        """Validate a raw dictionary against the schema."""
        return cls(**data)


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries without mutating the base."""
    import copy

    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
