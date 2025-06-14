from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base

# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------
try:
    _UUID_TYPE = UUID  # type: ignore
except ImportError:  # pragma: no cover
    _UUID_TYPE = String(36)


class RunStatus(str, enum.Enum):
    """Enumerated lifecycle states for a Run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    # Helpful alias because SQLAlchemy Enum produces upper-case names in check
    # constraints when using the default Enum naming conventions.  Having a
    # stable mapping avoids migration churn if we add/remove states later.


class RunORM(Base):
    """Persistent representation of a single execution *run*.

    A *run* represents an invocation of an agent (referenced via
    :class:`truss.core.models.run_session.RunSessionORM`) and tracks its
    lifecycle status alongside any error message.
    """

    __tablename__ = "runs"

    id = Column(_UUID_TYPE, primary_key=True, default=uuid.uuid4, nullable=False)

    # Foreign-key relationship to the parent session
    session_id = Column(
        _UUID_TYPE,
        ForeignKey("run_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(RunStatus, name="run_status_enum", native_enum=False),
        default=RunStatus.PENDING,
        nullable=False,
    )

    error = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ---------------------------------------------------------------------
    # Convenience helpers
    # ---------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RunORM id={self.id} session_id={self.session_id} status={self.status}>"
        ) 
