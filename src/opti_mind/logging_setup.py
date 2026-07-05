"""结构化日志初始化。启用 trace_id / workflow_id 可观测能力的基础。"""

from __future__ import annotations

import contextvars
import json
import logging
from typing import Any

TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)

_initialized = False


class _TraceIdFilter(logging.Filter):
    """在日志记录中注入当前请求的 trace_id。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = TRACE_ID.get() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    """输出 JSON 结构化日志：timestamp、level、logger、message、trace_id。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    level: str = "INFO", format: str = "text", *, force: bool = False
) -> None:  # noqa: A002
    """配置全局日志格式，幂等。

    Args:
        level: 日志级别，如 DEBUG/INFO/WARNING/ERROR。
        format: "text" 或 "json"，默认为 text。
        force: 是否强制重新配置（主要用于测试）。
    """
    global _initialized
    if _initialized and not force:
        return

    if format == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | trace_id=%(trace_id)s | %(message)s"
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_TraceIdFilter())

    root = logging.getLogger()
    root.setLevel(level.upper())

    if force:
        # 强制重新配置时移除已有的 StreamHandler，避免格式叠加。
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler):
                root.removeHandler(h)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)

    _initialized = True
