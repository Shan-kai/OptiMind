"""JSONL session event logger.

Each create/chat/get interaction appends one or more ``SessionEvent`` records to
``{base_dir}/{session_id}/events.jsonl``.  The log is append-only, ordered by an
auto-incrementing per-session sequence number, and is suitable for audit trails
and conversation replay.

This module intentionally does not depend on FastAPI or LangGraph.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from opti_mind.config import get_settings

logger = logging.getLogger(__name__)


_SESSION_EVENT_TYPES = [
    "user_message",
    "assistant_message",
    "tool_call",
    "tool_result",
    "state_update",
    "pipeline_run",
    "error",
]


class SessionEvent(BaseModel):
    """A single entry in the session JSONL log."""

    session_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sequence: int
    event_type: Literal[
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
        "state_update",
        "pipeline_run",
        "error",
    ]
    handler: str = Field(default="", description="Agent or handler name, e.g. field_mapping_agent")
    payload: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class SessionLogger:
    """Append-only JSONL logger for session events.

    The logger is thread-safe for concurrent writes to different sessions.
    Writes to the same file are serialized with a per-file lock.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or get_settings().session_log_dir)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def log(self, session_id: str, events: list[SessionEvent]) -> None:
        """Append a list of events to the session log."""
        if not events:
            return
        path = self._log_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._get_lock(str(path))
        with lock:
            next_seq = self._next_sequence(path)
            with path.open("a", encoding="utf-8") as f:
                for i, event in enumerate(events):
                    event.sequence = next_seq + i
                    f.write(event.model_dump_json() + "\n")

    def read(self, session_id: str) -> list[SessionEvent]:
        """Read all events for a session."""
        path = self._log_path(session_id)
        if not path.exists():
            return []
        events: list[SessionEvent] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(SessionEvent.model_validate_json(line))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping malformed log line: %s", exc)
        return events

    def _log_path(self, session_id: str) -> Path:
        return self.base_dir / session_id / "events.jsonl"

    def _get_lock(self, path: str) -> threading.Lock:
        with self._locks_lock:
            if path not in self._locks:
                self._locks[path] = threading.Lock()
            return self._locks[path]

    def _next_sequence(self, path: Path) -> int:
        if not path.exists():
            return 1
        count = 0
        with path.open("r", encoding="utf-8") as f:
            for _ in f:
                count += 1
        return count + 1


def convert_agent_events(
    session_id: str,
    handler: str,
    user_message: str,
    agent_events: list[dict[str, Any]],
    final_message: str,
) -> list[SessionEvent]:
    """Convert AgentLoop events and final message into SessionEvent entries."""
    type_map: dict[str, str] = {
        "message_delta": "assistant_message",
        "tool_start": "tool_call",
        "tool_end": "tool_result",
        "state_update": "state_update",
        "done": "pipeline_run",
        "error": "error",
    }
    events: list[SessionEvent] = []
    if user_message:
        events.append(
            SessionEvent(
                session_id=session_id,
                sequence=0,
                event_type="user_message",
                handler=handler,
                payload={"message": user_message},
            )
        )
    for raw in agent_events:
        mapped_type = type_map.get(raw.get("type", "error"), "error")
        ev = SessionEvent(
            session_id=session_id,
            sequence=0,
            event_type=cast(Any, mapped_type),
            handler=handler,
            payload=raw.get("payload", {}),
        )
        events.append(ev)
    if final_message:
        events.append(
            SessionEvent(
                session_id=session_id,
                sequence=0,
                event_type="assistant_message",
                handler=handler,
                payload={"message": final_message},
            )
        )
    return events


def convert_legacy_chat_action(
    session_id: str,
    user_message: str,
    action: Any,
) -> list[SessionEvent]:
    """Convert a legacy ChatAction into SessionEvent entries."""
    events: list[SessionEvent] = [
        SessionEvent(
            session_id=session_id,
            sequence=0,
            event_type="user_message",
            handler="legacy",
            payload={"message": user_message},
        )
    ]
    action_dict = action.model_dump() if hasattr(action, "model_dump") else dict(action)
    events.append(
        SessionEvent(
            session_id=session_id,
            sequence=0,
            event_type="state_update",
            handler="legacy",
            payload={"action": action_dict},
        )
    )
    return events


# Shared default logger used by AgentSession and the API layer.
session_logger = SessionLogger()
