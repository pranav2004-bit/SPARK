import uuid
from types import SimpleNamespace

from assessments.shuffling import shuffle_options, shuffle_questions_within_sections


def _fake_question(section_id, qid=None):
    return SimpleNamespace(section_id=section_id, id=qid or uuid.uuid4())


def _fake_option(oid=None, label="?", order=0):
    return SimpleNamespace(id=oid or uuid.uuid4(), label=label, order=order)


class TestShuffleQuestionsWithinSections:
    def test_empty_list_returns_empty_list(self):
        assert shuffle_questions_within_sections([], uuid.uuid4()) == []

    def test_single_question_returns_unchanged(self):
        q = _fake_question(section_id="s1")
        result = shuffle_questions_within_sections([q], uuid.uuid4())
        assert result == [q]

    def test_preserves_section_order_and_membership(self):
        s1, s2, s3 = "section-1", "section-2", "section-3"
        questions = (
            [_fake_question(s1) for _ in range(4)]
            + [_fake_question(s2) for _ in range(4)]
            + [_fake_question(s3) for _ in range(4)]
        )
        result = shuffle_questions_within_sections(questions, uuid.uuid4())
        assert [q.section_id for q in result] == [s1] * 4 + [s2] * 4 + [s3] * 4
        # Same set of question objects, just possibly reordered within a section.
        assert set(id(q) for q in result) == set(id(q) for q in questions)

    def test_deterministic_for_the_same_session_id(self):
        session_id = uuid.uuid4()
        questions = [_fake_question("s1", qid=f"q{i}") for i in range(6)]
        first = shuffle_questions_within_sections(list(questions), session_id)
        second = shuffle_questions_within_sections(list(questions), session_id)
        assert [q.id for q in first] == [q.id for q in second]

    def test_different_sessions_do_not_all_produce_the_same_order(self):
        # Probabilistic by nature of any shuffle, but with 8 items and 20
        # distinct session ids the chance every single one coincidentally
        # matches the canonical order is astronomically small — a real
        # failure here means the shuffle isn't actually randomizing.
        questions = [_fake_question("s1", qid=f"q{i}") for i in range(8)]
        orders = set()
        for _ in range(20):
            shuffled = shuffle_questions_within_sections(list(questions), uuid.uuid4())
            orders.add(tuple(q.id for q in shuffled))
        assert len(orders) > 1


class TestShuffleOptions:
    def test_empty_list_returns_empty_list(self):
        assert shuffle_options([], uuid.uuid4(), uuid.uuid4()) == []

    def test_single_option_still_gets_a_display_label(self):
        opt = _fake_option(label="A", order=1)
        result = shuffle_options([opt], uuid.uuid4(), uuid.uuid4())
        assert result == [opt]
        assert opt.display_label == "A"
        assert opt.display_order == 0

    def test_relabels_sequentially_regardless_of_original_label_order(self):
        # Original labels deliberately out of A/B/C/D order to prove the
        # NEW display_label is derived purely from final position, not
        # copied from whatever the admin originally called each option.
        options = [_fake_option(label=l, order=i) for i, l in enumerate(["D", "B", "A", "C"])]
        result = shuffle_options(options, uuid.uuid4(), uuid.uuid4())
        assert [o.display_label for o in result] == ["A", "B", "C", "D"]
        assert [o.display_order for o in result] == [0, 1, 2, 3]

    def test_never_mutates_the_original_label_or_order_fields(self):
        opt = _fake_option(label="B", order=2)
        shuffle_options([opt, _fake_option(label="A", order=1)], uuid.uuid4(), uuid.uuid4())
        assert opt.label == "B"
        assert opt.order == 2

    def test_deterministic_for_the_same_session_and_question(self):
        session_id, question_id = uuid.uuid4(), uuid.uuid4()
        options = [_fake_option(oid=f"opt{i}") for i in range(5)]
        first = shuffle_options(list(options), session_id, question_id)
        second = shuffle_options(list(options), session_id, question_id)
        assert [o.id for o in first] == [o.id for o in second]

    def test_different_questions_in_the_same_session_can_differ(self):
        # Same session, different question — must not always collapse to
        # the identical permutation just because the session id matches.
        session_id = uuid.uuid4()
        options = [_fake_option(oid=f"opt{i}") for i in range(6)]
        orders = set()
        for _ in range(20):
            shuffled = shuffle_options(list(options), session_id, uuid.uuid4())
            orders.add(tuple(o.id for o in shuffled))
        assert len(orders) > 1

    def test_more_than_26_options_falls_back_to_numeric_labels_without_crashing(self):
        options = [_fake_option(oid=f"opt{i}") for i in range(30)]
        result = shuffle_options(options, uuid.uuid4(), uuid.uuid4())
        assert len(result) == 30
        assert result[0].display_label in __import__("string").ascii_uppercase
        assert result[26].display_label == "27"
