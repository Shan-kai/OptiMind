import json
import logging

from opti_mind.logging_setup import TRACE_ID, _JsonFormatter, _TraceIdFilter, setup_logging


def test_setup_logging_text_format_does_not_raise() -> None:
    setup_logging(level="INFO", format="text", force=True)
    logger = logging.getLogger("test.text")
    logger.info("text format smoke test")


def test_setup_logging_json_format_does_not_raise() -> None:
    setup_logging(level="INFO", format="json", force=True)
    logger = logging.getLogger("test.json")
    logger.info("json format smoke test")


def test_trace_id_included_in_log_record() -> None:
    setup_logging(level="INFO", format="json", force=True)
    logger = logging.getLogger("test.trace")

    token = TRACE_ID.set("trace-123")
    try:
        assert TRACE_ID.get() == "trace-123"
        record = logger.makeRecord(
            name=logger.name,
            level=logging.INFO,
            fn="",
            lno=0,
            msg="record with trace",
            args=(),
            exc_info=None,
        )

        # 使用与 setup_logging 相同的 formatter/filter 验证输出
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        handler.addFilter(_TraceIdFilter())
        handler.filter(record)
        formatted = handler.format(record)

        payload = json.loads(formatted)
        assert payload["trace_id"] == "trace-123"
        assert payload["message"] == "record with trace"
    finally:
        TRACE_ID.reset(token)
