"""SQLAlchemy ORM model for the *agent_configs* table.

This mirrors :class:`truss.data_models.AgentConfig` but is designed for persistent
storage in Postgres.  Nested JSON structures such as *llm_config* and *tools*
are stored in JSON/JSONB columns.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON

from .base import Base


# Helper that chooses JSONB for Postgres, JSON otherwise ---------------------------------------
_JSON_TYPE = JSON  # Generic JSON works across dialects

try:
    _UUID_TYPE = UUID  # type: ignore
except ImportError:  # pragma: no cover
    _UUID_TYPE = String(36)  # Fallback for SQLite tests


class AgentConfigORM(Base):
    """Persistent representation of an agent configuration."""

    __tablename__ = "agent_configs"

    id = Column(_UUID_TYPE, primary_key=True, default=uuid.uuid4, nullable=False)
    name = Column(String(length=255), nullable=False)
    system_prompt = Column(Text, nullable=False)
    llm_config = Column(_JSON_TYPE, nullable=False)
    tools = Column(_JSON_TYPE, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # ---------------------------------------------------------------------
    # Convenience helpers
    # ---------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover
        return f"<AgentConfigORM id={self.id} name={self.name!r}>" 
