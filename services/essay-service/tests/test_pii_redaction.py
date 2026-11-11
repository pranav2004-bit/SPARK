from essays.pii_redaction import redact_pii


class TestRedactPii:
    def test_redacts_email(self):
        text, count = redact_pii("Contact me at jane.doe@example.com for details.")
        assert "jane.doe@example.com" not in text
        assert "[REDACTED_EMAIL]" in text
        assert count == 1

    def test_redacts_phone_number(self):
        text, count = redact_pii("Call me at (555) 123-4567 tomorrow.")
        assert "123-4567" not in text
        assert "[REDACTED_PHONE]" in text
        assert count == 1

    def test_redacts_dashed_ssn_as_id(self):
        text, count = redact_pii("My SSN is 123-45-6789, please don't share it.")
        assert "123-45-6789" not in text
        assert "[REDACTED_ID]" in text
        assert count == 1

    def test_redacts_bare_long_digit_run_as_id(self):
        text, count = redact_pii("My ID number is 123456789012 for reference.")
        assert "123456789012" not in text
        assert "[REDACTED_ID]" in text
        assert count == 1

    def test_multiple_patterns_all_redacted(self):
        text, count = redact_pii("Email jane@example.com or call 555-234-1000, SSN 123-45-6789.")
        assert count == 3
        assert "jane@example.com" not in text
        assert "123-45-6789" not in text

    def test_clean_text_untouched(self):
        original = "The causes of climate change are multifaceted and well-documented."
        text, count = redact_pii(original)
        assert text == original
        assert count == 0

    def test_never_logs_the_redacted_content_itself(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="essays.pii"):
            redact_pii("Reach me at secret.person@example.com")
        for record in caplog.records:
            assert "secret.person@example.com" not in record.getMessage()

    def test_empty_string(self):
        text, count = redact_pii("")
        assert text == ""
        assert count == 0


class TestPhoneRegexDoesNotFalsePositiveOnCommonEssayContent:
    """Real bug found and fixed during this phase's own audit: the
    original phone pattern matched on raw character-span length, not
    actual digit count, so a plain year range ("1990-2000") satisfied the
    same shape as a phone number and got redacted — degrading real
    evaluation quality for any essay discussing history or statistics,
    a very common, legitimate case. Fixed by requiring >= 9 actual
    digits, not just a 7-15-character span with separators."""

    def test_year_range_not_redacted(self):
        text, count = redact_pii("Climate change accelerated between 1990-2000 due to industrialization.")
        assert count == 0
        assert "1990-2000" in text

    def test_another_year_range_not_redacted(self):
        text, count = redact_pii("The policy was in effect from 2020-2023.")
        assert count == 0
        assert "2020-2023" in text

    def test_real_phone_number_still_redacted(self):
        text, count = redact_pii("Contact the office at 555-234-1000 for more information.")
        assert count == 1
        assert "[REDACTED_PHONE]" in text
        assert "555-234-1000" not in text


class TestIdRegexDoesNotFalsePositiveOnCommonEssayContent:
    """Real bug found and fixed by this phase's own 6th final-audit
    round — the exact same false-positive class the phone regex above was
    already fixed for: the bare-digit-run ID/SSN pattern matched on raw
    digit count alone, so any large, rounded quantitative figure a
    student writes in a statistics/economics/science essay (a population,
    a budget, a distance) satisfied the same shape as a 9-12 digit
    SSN/Aadhaar-style ID and got silently redacted — degrading real
    evaluation quality for exactly the essays this platform expects.
    Confirmed empirically before being fixed. Fixed by treating a bare
    digit run ending in 3+ zeros as a rounded figure, not a genuine ID —
    real SSNs/Aadhaar numbers are effectively random and vanishingly
    unlikely to end in three zeros."""

    def test_population_figure_not_redacted(self):
        text, count = redact_pii("The global population reached 1400000000 people by 2023.")
        assert count == 0
        assert "1400000000" in text

    def test_budget_figure_not_redacted(self):
        text, count = redact_pii("The national budget allocated 500000000 dollars to healthcare.")
        assert count == 0
        assert "500000000" in text

    def test_bare_id_not_ending_in_zeros_still_redacted(self):
        text, count = redact_pii("My ID number is 123456789012 for reference.")
        assert count == 1
        assert "[REDACTED_ID]" in text
        assert "123456789012" not in text

    def test_dashed_ssn_ending_in_zeros_still_redacted(self):
        # The zero-suffix carve-out only applies to the bare-digit-run
        # branch — a dashed SSN is unambiguous regardless of its digits.
        text, count = redact_pii("My SSN is 123-45-6000, please don't share it.")
        assert count == 1
        assert "[REDACTED_ID]" in text
        assert "123-45-6000" not in text
