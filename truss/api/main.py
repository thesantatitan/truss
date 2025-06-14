from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from temporalio.client import Client, TLSConfig  # type: ignore
from pydantic import BaseModel

from truss.core.storage import PostgresStorage
from truss.core.models.base import Base

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_temporal_url() -> str:
    """Return the Temporal endpoint URL from environment or default."""
    return os.getenv("TEMPORAL_URL", "localhost:7233")


async def _connect_temporal(url: str) -> Client:
    """Establish an async connection to Temporal.

    A thin wrapper so that connection logic can be monkey-patched in tests.
    """
    # In most setups plaintext is used for local development.  If the user
    # provides `TEMPORAL_TLS_ENABLED=true`, we assume TLS with default config.
    if os.getenv("TEMPORAL_TLS_ENABLED", "false").lower() in {"1", "true", "yes"}:
        logger.info("Connecting to Temporal with TLS enabled at %s", url)
        return await Client.connect(url, tls=TLSConfig())

    logger.info("Connecting to Temporal at %s", url)
    return await Client.connect(url)


app = FastAPI(title="Truss Agent Execution API", version="0.1.0")

# Global handle – populated on application startup
_temporal_client: Optional[Client] = None
# Storage handle (sync) – used directly by API routes
_storage: Optional[PostgresStorage] = None


@app.on_event("startup")
async def _startup_event() -> None:  # noqa: D401
    """FastAPI startup hook establishing Temporal connection.

    For test environments (``pytest``) you can set ``SKIP_TEMPORAL_CONNECTION=1``
    to bypass the network call and speed up the test suite.
    """
    global _temporal_client
    global _storage

    if os.getenv("SKIP_TEMPORAL_CONNECTION", "0") in {"1", "true", "yes"}:
        logger.info("Skipping Temporal connection – SKIP_TEMPORAL_CONNECTION flag set")
    else:
        url = _get_temporal_url()
        try:
            _temporal_client = await _connect_temporal(url)
            logger.info("Successfully connected to Temporal: %s", url)
        except Exception:  # pragma: no cover – connection issues caught for observability
            logger.exception("Failed to connect to Temporal at %s", url)
            # Intentionally swallow the error to allow the API to boot even if Temporal
            # is unavailable; endpoints that rely on the client must check for None.
            _temporal_client = None

    # ---------------------------------------------
    # Initialise PostgresStorage
    # ---------------------------------------------
    db_url = os.getenv("DATABASE_URL", "sqlite:///truss.db")
    try:
        storage = PostgresStorage.from_database_url(db_url)
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to initialise SQLAlchemy engine: %s", exc)
        return

    # Ensure schema exists in dev/test environments (SQLite especially)
    if db_url.startswith("sqlite"):
        Base.metadata.create_all(storage._engine)  # type: ignore[attr-defined]

    _storage = storage


@app.on_event("shutdown")
async def _shutdown_event() -> None:  # noqa: D401
    """Cleanly close Temporal connection on app shutdown."""
    global _temporal_client
    global _storage
    if _temporal_client is not None:
        await _temporal_client.close()
        _temporal_client = None

    _storage = None


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:  # noqa: D401 – simple health check
    """Return a basic healthcheck payload."""
    return {"status": "ok"}


# --------------------------------------------------------------------------------------
# Public utility functions
# --------------------------------------------------------------------------------------


def get_temporal_client() -> Client:
    """Return the live Temporal client instance.

    Raises:
        RuntimeError: If the client has not been initialised yet (e.g. during
            application startup failure or when the connection is intentionally
            skipped in tests).
    """
    if _temporal_client is None:
        raise RuntimeError("Temporal client has not been initialised."
                           " Ensure the FastAPI startup event has completed.")
    return _temporal_client


# -----------------------------------------------------------------------------
# Storage dependency & helper
# -----------------------------------------------------------------------------


def get_storage() -> PostgresStorage:
    """Return the active :class:`PostgresStorage` instance."""
    if _storage is None:  # pragma: no cover – should be initialised on startup
        raise RuntimeError("Storage has not been initialised."
                           " Ensure FastAPI startup completed successfully.")
    return _storage


# -----------------------------------------------------------------------------
# Request/response models
# -----------------------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    agent_id: str  # UUID string
    user_id: str


class SessionCreateResponse(BaseModel):
    session_id: str


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@app.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionCreateResponse)
def create_session(
    payload: SessionCreateRequest,
    storage: PostgresStorage = Depends(get_storage),
):
    """Create a new conversation session and return its ID."""

    from uuid import UUID

    try:
        session_obj = storage.create_session(
            agent_config_id=UUID(payload.agent_id), user_id=payload.user_id
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return SessionCreateResponse(session_id=str(session_obj.id)) 
