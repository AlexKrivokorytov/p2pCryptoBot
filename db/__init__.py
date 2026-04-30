"""Database package — exposes Base for Alembic model discovery.

Session factory and engine are created in bot/main.py to allow proper
dependency injection and avoid global state.
"""

from db.models.base import Base

__all__ = ["Base"]
