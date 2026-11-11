"""LIVETRACKER4 H1 and H4: checklist tests.

Each row of the section 2.13 security matrix and the section 2.14 resilience
table must name the tests that prove it. A row with no test must appear in
KNOWN_GAPS with a reason, so a missing test is visible and never silent.
The checklist fails if a named test does not exist.
"""
import pathlib
import re

import pytest

TESTS = pathlib.Path(__file__).resolve().parent

SECURITY_MATRIX = {
    "Unauthorized access": [
        "test_content_api.py::test_anonymous_is_401",
        "test_content_api.py::test_student_is_403_on_every_admin_endpoint",
    ],
    "Cross-tenant access (IDOR)": [
        "test_content_api.py::test_cross_institution_node_is_404_not_403",
        "test_content_api.py::test_cross_institution_question_is_404",
    ],
    "Stored XSS": [
        "test_content_hardening.py::test_script_payload_stored_and_returned_as_plain_text",
    ],
    "Malicious upload (path traversal, polyglot)": [
        "test_content_images.py::test_path_traversal_key_refused",
        "test_content_images.py::test_oversized_image_is_413_and_object_deleted",
        "test_content_images.py::test_disallowed_extension_400",
        "test_content_images.py::test_bad_contents_deleted_and_400",
    ],
    "Mass assignment": [
        "test_content_api.py::test_mass_assignment_ignored",
    ],
    "Answer-key leakage": [
        "test_content_hardening.py::test_admin_list_responses_never_include_answer_key",
        "test_content_api.py::test_list_hides_answer_key_detail_shows_it_to_admin",
    ],
    "Scraping / bulk exfiltration (rate limit)": [
        "test_content_phase_fg.py::test_user_limit_returns_429_with_retry_after",
    ],
    "Race conditions": [
        "test_content_concurrency.py::test_two_concurrent_patches_one_wins_one_gets_412",
        "test_content_concurrency.py::test_two_concurrent_publishes_make_one_state_change",
        "test_content_concurrency.py::test_concurrent_reorders_leave_one_complete_order",
    ],
    "Audit tampering": [
        "test_content_api.py::test_audit_has_no_update_or_delete_route",
    ],
    "Log leakage": [
        "test_content_security.py::test_no_logging_of_question_or_option_text",
        "test_content_phase_fg.py::test_no_question_or_option_text_in_any_content_log",
    ],
    "CSRF": [
        "test_content_hardening.py::test_cookie_only_request_is_rejected",
    ],
    "Denial of service via large text": [
        "test_content_services.py::test_text_at_max_accepted_and_one_over_refused",
    ],
    "SQL injection": [
        "test_content_security.py::test_no_raw_sql_in_content_module",
    ],
}

RESILIENCE_TABLE = {
    "DB down": ["test_content_hardening.py::test_database_outage_returns_503_not_500"],
    "S3 down": ["test_content_images.py::test_storage_not_configured_503",
                "test_content_phase_fg.py::test_botocore_timeout_during_verify_is_503_and_object_kept",
                "test_content_phase_fg.py::test_content_timeout_is_applied_to_the_client_config",
                "test_content_images.py::test_storage_outage_during_verify_is_503_and_object_kept"],
    "Redis down": ["test_content_ops.py::test_cache_read_failure_falls_through_to_database",
                   "test_content_phase_fg.py::test_redis_error_fails_open_and_logs_warning"],
    "Publish crashes mid-way": ["test_content_hardening.py::test_publish_crash_mid_way_rolls_back_everything",
                                "test_content_hardening.py::test_retry_after_crash_succeeds"],
    "Duplicate request": ["test_content_hardening.py::test_double_click_publish_is_idempotent"],
    "Stale editor": ["test_content_api.py::test_patch_with_stale_etag_412_then_fresh_ok"],
    "Bad deploy (flag off)": ["test_content_api.py::test_all_endpoints_404_when_flag_off"],
    "Rollback (flag off, data kept)": ["test_content_phase_fg.py::test_flag_off_hides_content_and_flag_on_restores_it_with_no_data_loss"],
    "Accidental mass delete": ["test_content_services.py::test_delete_node_blocked_when_it_has_children_or_questions",
                               "test_content_services.py::test_audit_rows_survive_question_delete"],
}

# Rows whose specified behaviour is not built as written. Empty: every row is built and tested.
# Closed in LIVETRACKER4 H1/H4: image statuses now 415/413 (section 2.13); S3 client timeout is
# explicit for content calls (CONTENT_S3_TIMEOUT_SECONDS, section 2.14).
KNOWN_GAPS = {}


def _defined_tests():
    names = set()
    for path in TESTS.glob("test_content_*.py"):
        for name in re.findall(r"^\s*def (test_\w+)\(", path.read_text(encoding="utf-8"), re.MULTILINE):
            names.add(f"{path.name}::{name}")
    return names


@pytest.mark.parametrize("row", sorted(SECURITY_MATRIX))
def test_security_matrix_row_has_its_tests(row):
    assert SECURITY_MATRIX[row], f"{row} has no tests and is not in KNOWN_GAPS"
    defined = _defined_tests()
    missing = [t for t in SECURITY_MATRIX[row] if t not in defined]
    assert missing == []


@pytest.mark.parametrize("row", sorted(RESILIENCE_TABLE))
def test_resilience_row_has_its_tests(row):
    defined = _defined_tests()
    missing = [t for t in RESILIENCE_TABLE[row] if t not in defined]
    assert missing == []


def test_no_known_gaps_remain():
    # A new spec gap must be fixed or added here with a reason; an empty dict is the expected state.
    assert KNOWN_GAPS == {}
