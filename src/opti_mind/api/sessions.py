"""Session-based conversational API for OptiMind.

This module provides the endpoints used by the chat-style frontend:

- POST /api/v1/sessions       : upload a data file and start a session
- POST /api/v1/sessions/{id}/chat : send a chat message
- GET  /api/v1/sessions/{id}  : get current session state and chat history

All session lifecycle logic lives in ``opti_mind.chat.session.AgentSession``;
this file is only responsible for HTTP concerns.

The old /optimize / /resume endpoints remain available in routes.py for
backward compatibility.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from opti_mind.chat.i18n import CHAT_STRINGS
from opti_mind.chat.models import ChatMessage, ChatRequest, SessionResponse
from opti_mind.chat.session import AgentSession, AgentSessionError
from opti_mind.chat.session_logger import SessionEvent, session_logger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["sessions"])

UPLOAD_DIR = Path("uploads")


def cleanup_old_uploads(upload_dir: Path, ttl_seconds: int) -> None:
    """删除超过 ttl_seconds 的上传会话目录。"""
    if not upload_dir.exists():
        return
    cutoff = time.time() - ttl_seconds
    for subdir in upload_dir.iterdir():
        if not subdir.is_dir():
            continue
        try:
            if subdir.stat().st_mtime < cutoff:
                shutil.rmtree(subdir)
                logger.info("Cleaned up old upload directory: %s", subdir)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to clean up upload directory: %s", subdir)


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    file: Annotated[UploadFile, File(description="CSV data file")],
    business_goal: str = Form(default=""),
    problem_type: str | None = Form(default=None),
    scenarios: str | None = Form(default=None),
) -> SessionResponse:
    """Upload a data file and start an optimization session."""
    session_id = str(uuid4())
    upload_path = UPLOAD_DIR / session_id
    upload_path.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(file.filename or "data.csv")
    file_path = upload_path / safe_name
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    initial_state: dict[str, Any] = {
        "errors": [],
        "source": str(file_path),
        "session_id": session_id,
        "business_goal": business_goal or None,
        "scenarios": _parse_scenarios(scenarios),
        "chat_history": [
            ChatMessage.create("assistant", CHAT_STRINGS.session_welcome).model_dump()
        ],
    }
    if problem_type:
        initial_state["problem_type"] = problem_type

    session = AgentSession(session_id=session_id)
    try:
        state = session.create(initial_state)
    except AgentSessionError as exc:
        logger.exception("Session startup failed")
        return _error_response(session_id, [str(exc)])

    return session.build_response(state)


@router.post("/sessions/{session_id}/chat", response_model=SessionResponse)
async def chat(session_id: str, request: ChatRequest) -> SessionResponse:
    """Send a chat message to an existing session."""
    session_id = session_id.strip()
    session = AgentSession(session_id=session_id)

    try:
        state = session.chat(request.message)
    except AgentSessionError as exc:
        if str(exc) == "session_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            ) from exc
        logger.exception("Chat turn failed")
        return _error_response(session_id, [str(exc)])

    return session.build_response(state)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    """Get the current state, chat history, and result of a session."""
    session_id = session_id.strip()
    session = AgentSession(session_id=session_id)
    state = session.get_state()
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session.build_response(state)


@router.get("/sessions/{session_id}/events", response_model=list[SessionEvent])
async def get_session_events(session_id: str) -> list[SessionEvent]:
    """Return the JSONL event log for a session.

    The log is append-only and ordered by sequence number. It captures the
    full lifecycle of agent turns: user messages, tool calls, tool results,
    state updates, pipeline runs, and errors.
    """
    session_id = session_id.strip()
    session = AgentSession(session_id=session_id)
    if not session.get_state():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session_logger.read(session_id)


def _error_response(session_id: str, errors: list[str]) -> SessionResponse:
    """Build an error response for the given session."""
    return SessionResponse(
        session_id=session_id,
        status="error",
        messages=[],
        errors=errors,
    )


def _parse_scenarios(scenarios: str | None) -> list[dict[str, Any]] | None:
    """Parse the scenarios form field from JSON string to list."""
    if not scenarios:
        return None
    try:
        data = json.loads(scenarios)
        if isinstance(data, list):
            return data
        return [data]
    except json.JSONDecodeError:
        return None


def _safe_filename(name: str) -> str:
    """Remove path traversal and dangerous characters from an uploaded filename."""
    name = Path(name).name
    keep_chars = (" ", ".", "_", "-")
    return "".join(c for c in name if c.isalnum() or c in keep_chars) or "data.csv"
