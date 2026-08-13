"""
Task 13.2 — structured logging + correlation ID.

The genuine end-to-end proof for this task (nginx's own X-Request-ID
matching this service's JSON log lines matching the client-visible
response header, plus a real Celery task run's own task_id doing the same
for its log lines) was done live against the real Docker stack — see
LIVETRACKER2_V1.md's Task 13.2 notes for the exact commands and real
output. These tests cover the same logic at the unit level, so a
regression here is caught by the normal test suite without needing the
full stack running.
"""
import json
import logging

from rest_framework.test import APIClient

from core.logging_utils import (
    CorrelationIdLogFilter, JSONFormatter, bind_request_id, get_request_id,
)


class TestBindRequestId:
    def test_get_request_id_is_none_outside_any_binding(self, db):
        assert get_request_id() is None

    def test_bind_request_id_sets_and_restores(self, db):
        assert get_request_id() is None
        with bind_request_id("abc-123"):
            assert get_request_id() == "abc-123"
        assert get_request_id() is None

    def test_bind_request_id_nesting_restores_outer_value(self, db):
        with bind_request_id("outer"):
            with bind_request_id("inner"):
                assert get_request_id() == "inner"
            assert get_request_id() == "outer"


class TestCorrelationIdMiddleware:
    def test_response_echoes_x_request_id_header(self, db):
        client = APIClient()
        resp = client.get("/api/assessments/health/", HTTP_X_REQUEST_ID="my-custom-id")
        assert resp["X-Request-ID"] == "my-custom-id"

    def test_generates_one_when_none_supplied(self, db):
        client = APIClient()
        resp = client.get("/api/assessments/health/")
        assert resp["X-Request-ID"]  # non-empty, some UUID was generated

    def test_different_requests_get_different_ids_when_unsupplied(self, db):
        client = APIClient()
        resp1 = client.get("/api/assessments/health/")
        resp2 = client.get("/api/assessments/health/")
        assert resp1["X-Request-ID"] != resp2["X-Request-ID"]


class TestJSONFormatter:
    def _make_record(self, msg="hello", level=logging.INFO, **extra):
        record = logging.LogRecord(
            name="test.logger", level=level, pathname=__file__, lineno=1,
            msg=msg, args=(), exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_output_is_valid_json_with_expected_fields(self):
        formatter = JSONFormatter()
        record = self._make_record("test message")
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert "timestamp" in parsed

    def test_request_id_defaults_to_none_when_unset(self):
        formatter = JSONFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert parsed["request_id"] is None

    def test_correlation_filter_stamps_request_id_from_context(self):
        formatter = JSONFormatter()
        log_filter = CorrelationIdLogFilter()
        record = self._make_record()
        with bind_request_id("filter-test-id"):
            log_filter.filter(record)
            parsed = json.loads(formatter.format(record))
        assert parsed["request_id"] == "filter-test-id"

    def test_extra_fields_are_included(self):
        formatter = JSONFormatter()
        record = self._make_record(task_name="my_task", attempts=3)
        parsed = json.loads(formatter.format(record))
        assert parsed["task_name"] == "my_task"
        assert parsed["attempts"] == 3
