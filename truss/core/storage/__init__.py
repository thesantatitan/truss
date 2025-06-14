"""Storage abstractions for persisting and retrieving Truss runtime data.

Currently provides a thin `PostgresStorage` class that wraps synchronous SQLAlchemy
operations.  All public methods are designed to be thread-safe so they can be
invoked from Temporal activities via `anyio.to_thread.run_sync`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, List, Optional
from uuid import UUID

from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from truss.core.models.agent_config import AgentConfigORM
from truss.core.models.run import RunORM, RunStatus
from truss.core.models.run_session import RunSessionORM
from truss.core.models.run_step import RunStepORM, MessageRole
from truss.data_models import Message, AgentMemory, AgentConfig

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


class PostgresStorage:  # noqa: WPS110 – Name dictated by technical spec
    """Concrete storage implementation backed by a Postgres database.

    Parameters
    ----------
    engine
        SQLAlchemy *Engine* instance connected to the target Postgres (or
        compatible) database.
    """

    def __init__(self, engine: Engine) -> None:  # noqa: D401 – imperative mood OK
        self._engine: Engine = engine
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    # ------------------------------------------------------------------
    # Context-manager helper
    # ------------------------------------------------------------------
    @contextmanager
    def _session_scope(self) -> Iterable[Session]:  # type: ignore[override]
        """Provide a transactional scope around a series of operations."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:  # noqa: BLE001 – re-raise downstream
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # CRUD helpers used by StorageActivities
    # ------------------------------------------------------------------
    def create_run(self, session_id: UUID) -> RunORM:
        """Insert a new *Run* row and return the ORM instance."""
        with self._session_scope() as session:
            run = RunORM(session_id=session_id, status=RunStatus.PENDING)
            session.add(run)
            session.flush()  # populate PK
            session.refresh(run)
            return run

    def create_run_step_from_message(self, run_id: UUID, message: Message) -> RunStepORM:
        """Persist a Pydantic *Message* as a *RunStep* row."""
        tool_calls_json = (
            [tool_call.model_dump() for tool_call in message.tool_calls]
            if message.tool_calls
            else None
        )
        with self._session_scope() as session:
            step = RunStepORM(
                run_id=run_id,
                role=MessageRole(message.role),
                content=message.content,
                tool_calls=tool_calls_json,
                tool_call_id=message.tool_call_id,
            )
            session.add(step)
            session.flush()
            session.refresh(step)
            return step

    def get_steps_for_session(self, session_id: UUID) -> List[RunStepORM]:
        """Return all *RunStep* rows for a given *RunSession*, ordered chronologically."""
        with self._session_scope() as session:
            stmt = (
                select(RunStepORM)
                .join(RunORM, RunStepORM.run_id == RunORM.id)
                .where(RunORM.session_id == session_id)
                .order_by(RunStepORM.created_at)
            )
            return list(session.execute(stmt).scalars())

    def update_run_status(self, run_id: UUID, status: str, error: Optional[str] = None) -> None:
        """Update *Run.status* (and optionally *error*) atomically."""
        with self._session_scope() as session:
            stmt = (
                update(RunORM)
                .where(RunORM.id == run_id)
                .values(status=status, error=error)
            )
            session.execute(stmt)

    def load_agent_config(self, agent_id: UUID) -> AgentConfig:
        """Fetch :class:`AgentConfig` Pydantic model for a given identifier."""
        with self._session_scope() as session:
            obj = session.get(AgentConfigORM, agent_id)
            if obj is None:  # pragma: no cover
                raise KeyError(f"AgentConfig {agent_id} not found")
            return AgentConfig(
                id=str(obj.id),
                name=obj.name,
                system_prompt=obj.system_prompt,
                llm_config=obj.llm_config,  # type: ignore[arg-type]
                tools=obj.tools,
            )

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    def create_session(self, agent_config_id: UUID, user_id: str) -> RunSessionORM:
        """Insert a new :class:`RunSessionORM` row and return the instance."""

        # Validate agent exists – provides nicer error than FK violation.
        with self._session_scope() as session:
            if session.get(AgentConfigORM, agent_config_id) is None:
                raise KeyError(f"AgentConfig {agent_config_id} not found")

            session_obj = RunSessionORM(agent_config_id=agent_config_id, user_id=user_id)
            session.add(session_obj)
            session.flush()
            session.refresh(session_obj)
            return session_obj

    # ------------------------------------------------------------------
    # Factory helper (optional)
    # ------------------------------------------------------------------
    @classmethod
    def from_database_url(cls, url: str) -> "PostgresStorage":
        """Create a :class:`PostgresStorage` from database URL."""
        engine = create_engine(url, future=True)
        return cls(engine)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------
    def get_session(self, session_id: UUID) -> RunSessionORM:
        """Return :class:`RunSessionORM` or raise ``KeyError`` if missing."""
        with self._session_scope() as session:
            obj = session.get(RunSessionORM, session_id)
            if obj is None:
                raise KeyError(f"RunSession {session_id} not found")
            return obj
