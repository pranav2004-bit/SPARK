"""
pii_redaction.py — Task 5.2 / ADR 003 Decision 4.

New essay-service code, not a CLAP port (see that ADR's own correction
note — a direct read of CLAP's actual source found no PII redaction
anywhere in it). Three regex patterns applied unconditionally before any
essay text leaves this service for the LLM provider, regardless of which
provider Decision 1 ever changes to. Logs only a redaction COUNT, never
the matched content itself — the point of redacting is defeated if the
redacted values end up in a log line instead.
"""
import logging
import re

logger = logging.getLogger("essays.pii")


def _is_rounded_bare_number(s: str) -> bool:
    """A bare (no dashes/spaces/dots/parens — a single unbroken run of
    digits, optionally with a leading +) number ending in 3+ zeros. Real
    SSNs/Aadhaar IDs and real phone numbers WRITTEN WITH SEPARATORS
    (555-234-1000) are unambiguous regardless of trailing zeros — a human
    deliberately punctuated them as an identifier. A bare, unbroken run of
    digits ending in three or more zeros is virtually always a rounded
    quantitative figure (population, budget, distance) a student wrote in
    their own essay prose, not a genuine ID or phone number, which are
    effectively random digit sequences with no reason to be round."""
    digits_only = s.lstrip("+")
    return digits_only.isdigit() and digits_only.endswith("000")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Phone-shaped: a run of digits (optionally grouped with spaces/dashes/
# dots/parens, optional leading +) whose ACTUAL DIGIT COUNT — not string
# length — is 9-15. Checked in code (_MIN_PHONE_DIGITS below), not the
# regex alone: a plain digit-count regex can't distinguish "how many
# digits" from "how long is the matched span" when separators are mixed
# in, and the original 7-15-*character* version matched common,
# genuinely-non-PII essay content — "1990-2000", "2020-2023" — as if it
# were a phone number, degrading real evaluation quality (the LLM would
# see [REDACTED_PHONE] instead of a legitimate year range in an essay
# about history or statistics). A real minimum of 9 actual digits keeps
# catching real phone numbers (10 digits is the common case) while no
# longer flagging a plain 8-digit year range.
_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)(\+?\d[\d\-.\s()]{6,14}\d)(?!\w)")
_MIN_PHONE_DIGITS = 9
# SSN/ID-shaped: a bare run of 9-12 digits (e.g. SSN, Aadhaar-style ID),
# with or without dashes in the classic 3-2-4 SSN grouping.
_ID_RE = re.compile(r"(?<!\w)(\d{3}-\d{2}-\d{4}|\d{9,12})(?!\w)")


def redact_pii(text: str) -> tuple[str, int]:
    """Returns (redacted_text, redaction_count). Order matters:
    1. Email first, so an email's own local-part digits never get
       double-matched by the phone/ID patterns after the @-address is
       already replaced.
    2. ID before phone, not the ADR's listed order — a classic dashed SSN
       (123-45-6789) also structurally satisfies the broader phone-shaped
       pattern (digits with dash/space/paren separators), so ID's more
       specific dashed/bare-digit-run shape must get first claim on it or
       every SSN-shaped sequence would be mislabeled as a phone number.
       Both patterns redact either way — this only affects which
       placeholder a given match ends up under."""
    count = 0

    def _sub(pattern, replacement, s):
        nonlocal count
        new_s, n = pattern.subn(replacement, s)
        count += n
        return new_s

    def _phone_replacer(match):
        nonlocal count
        raw = match.group(0)
        digit_count = sum(1 for ch in raw if ch.isdigit())
        if digit_count < _MIN_PHONE_DIGITS:
            return raw  # not phone-shaped enough — leave it (e.g. a year range)
        # Real gap found by this phase's own 6th final-audit round,
        # discovered while fixing the identical class of bug in
        # _id_replacer below: a bare (unpunctuated) large number like
        # "1400000000" satisfies THIS pattern too (digits interspersed
        # with optional separators still matches a pure digit run), so
        # exempting it only from the ID pattern wasn't enough — it just
        # fell through and got redacted as [REDACTED_PHONE] instead of
        # [REDACTED_ID]. See _is_rounded_bare_number's own docstring for
        # the reasoning; a real phone number written WITH separators
        # (555-234-1000) is unaffected, since that check only exempts a
        # bare, unpunctuated digit run.
        if _is_rounded_bare_number(raw):
            return raw
        count += 1
        return "[REDACTED_PHONE]"

    def _id_replacer(match):
        nonlocal count
        digits = match.group(0)
        # Real gap found by this phase's own 6th final-audit round — the
        # exact same false-positive class already fixed once for the phone
        # pattern above ("1990-2000", "2020-2023"): the bare digit-run
        # branch this pattern models on SSN/Aadhaar-style IDs also matches
        # any large, rounded quantitative figure a student writes in their
        # own essay. Confirmed empirically: "The global population
        # reached 1400000000 people" was being silently redacted to
        # "[REDACTED_ID]" before ever reaching the LLM — degrading real
        # evaluation quality on exactly the statistics/economics/science
        # essays this platform expects, the same harm class as the phone
        # bug. The dashed-SSN branch (123-45-6789) is untouched: it's not
        # a bare digit run, so _is_rounded_bare_number never exempts it.
        if _is_rounded_bare_number(digits):
            return digits
        count += 1
        return "[REDACTED_ID]"

    redacted = text
    redacted = _sub(_EMAIL_RE, "[REDACTED_EMAIL]", redacted)
    redacted = _ID_RE.sub(_id_replacer, redacted)
    redacted = _PHONE_CANDIDATE_RE.sub(_phone_replacer, redacted)

    if count:
        logger.info("redact_pii: %d PII pattern(s) redacted before outbound LLM call.", count)

    return redacted, count
