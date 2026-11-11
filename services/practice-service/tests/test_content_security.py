import pathlib

import content

CONTENT_DIR = pathlib.Path(content.__file__).parent


def _content_sources():
    return [p for p in CONTENT_DIR.rglob("*.py") if "migrations" not in p.parts]


def test_no_raw_sql_in_content_module():
    # LIVETRACKER4 section 2.13: ORM only, no raw SQL in the content module.
    #
    # One deliberate, documented exception: content/services.py's single
    # cursor.execute call acquires a Postgres advisory lock (serializes
    # concurrent reorder operations — the H2 concurrency fix). The ORM has
    # no equivalent for pg_advisory_xact_lock, so this is the only way to
    # get it; it's safely parameterized (%s placeholder, not string-built
    # SQL), so it carries no injection risk. Allowed by exact line content,
    # not by filename, so any OTHER raw SQL added later — in this file or
    # any other — still fails this test.
    ALLOWED_RAW_SQL = 'cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [key])'

    offenders = []
    for path in _content_sources():
        text = path.read_text(encoding="utf-8")
        for needle in (".raw(", "cursor.execute", "RawSQL", "extra("):
            if needle in text and not (needle == "cursor.execute" and ALLOWED_RAW_SQL in text and text.count("cursor.execute") == 1):
                offenders.append(f"{path.name}: {needle}")
    assert offenders == []


def test_no_logging_of_question_or_option_text():
    # Logs carry ids and status only (section 2.15). Any logger call that interpolates
    # question_text or option_text is a leak.
    offenders = []
    for path in _content_sources():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "logger." in line and ("question_text" in line or "option_text" in line):
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == []
