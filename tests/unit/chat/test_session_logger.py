"""Tests for the JSONL session logger."""

from __future__ import annotations

from pathlib import Path

from opti_mind.chat.session_logger import SessionEvent, SessionLogger, convert_agent_events


def test_logger_appends_events(tmp_path: Path) -> None:
    """Events are appended to the session JSONL file with incrementing sequences."""
    logger = SessionLogger(base_dir=tmp_path)
    events = [
        SessionEvent(session_id="s1", sequence=0, event_type="user_message", handler="test"),
        SessionEvent(session_id="s1", sequence=0, event_type="assistant_message", handler="test"),
    ]
    logger.log("s1", events)
    logger.log(
        "s1", [SessionEvent(session_id="s1", sequence=0, event_type="tool_call", handler="test")]
    )

    read_back = logger.read("s1")
    assert len(read_back) == 3
    assert read_back[0].sequence == 1
    assert read_back[1].sequence == 2
    assert read_back[2].sequence == 3


def test_logger_isolates_sessions(tmp_path: Path) -> None:
    """Different sessions write to different files."""
    logger = SessionLogger(base_dir=tmp_path)
    logger.log(
        "s1", [SessionEvent(session_id="s1", sequence=0, event_type="user_message", handler="test")]
    )
    logger.log(
        "s2", [SessionEvent(session_id="s2", sequence=0, event_type="user_message", handler="test")]
    )

    assert len(logger.read("s1")) == 1
    assert len(logger.read("s2")) == 1


def test_read_missing_session_returns_empty(tmp_path: Path) -> None:
    """Reading a session with no log file returns an empty list."""
    logger = SessionLogger(base_dir=tmp_path)
    assert logger.read("missing") == []


def test_convert_agent_events_includes_user_and_final() -> None:
    """convert_agent_events produces user, tool, and assistant events."""
    events = convert_agent_events(
        session_id="s1",
        handler="field_mapping_agent",
        user_message="hello",
        agent_events=[{"type": "tool_start", "payload": {"tool": "propose_mapping"}}],
        final_message="ok",
    )
    assert len(events) == 3
    assert events[0].event_type == "user_message"
    assert events[1].event_type == "tool_call"
    assert events[2].event_type == "assistant_message"
    assert events[2].payload["message"] == "ok"
