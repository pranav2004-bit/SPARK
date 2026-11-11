import uuid
from unittest.mock import patch

import pytest

from content import services as svc
from content.errors import ContentError
from content.models import (
    ContentAuditEvent, ContentNode, ContentQuestion, ContentQuestionVersion, ContentQuestionUsage,
    NODE_PUBLISHED, NODE_RETIRED, QUESTION_DRAFT, QUESTION_PUBLISHED, QUESTION_RETIRED,
    VERSION_DRAFT, VERSION_IN_REVIEW, VERSION_PUBLISHED,
)
from tests.conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID

ACTOR = ADMIN_USER_ID
OK_OPTIONS = [
    {"option_text": "Alpha", "is_correct": True},
    {"option_text": "Beta", "is_correct": False},
    {"option_text": "Gamma", "is_correct": False},
    {"option_text": "Delta", "is_correct": False},
]


def _subject(name="Reasoning", inst=INSTITUTION_A, publish=True):
    node = svc.create_node(institution_id=inst, actor_id=ACTOR, name=name)
    if publish:
        svc.publish_node(institution_id=inst, actor_id=ACTOR, node_id=node.id)
    return ContentNode.objects.get(pk=node.id)


def _topic(parent, name="Puzzles", publish=True):
    node = svc.create_node(institution_id=parent.institution_id, actor_id=ACTOR, name=name, parent_id=parent.id)
    if publish:
        svc.publish_node(institution_id=parent.institution_id, actor_id=ACTOR, node_id=node.id)
    return ContentNode.objects.get(pk=node.id)


def _question(topic, text="What is 2+2?", options=None):
    q, v = svc.create_question(
        institution_id=topic.institution_id, actor_id=ACTOR, node_id=topic.id,
        text=text, options=options if options is not None else OK_OPTIONS,
    )
    return ContentQuestion.objects.get(pk=q.id), ContentQuestionVersion.objects.get(pk=v.id)


def _etag(question):
    return svc.etag_for(svc.editable_version(question))


@pytest.fixture
def topic(db):
    return _topic(_subject())


# ── nodes ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestNodes:
    def test_create_root_and_child(self):
        root = _subject()
        child = _topic(root)
        assert child.parent_id == root.id

    def test_child_name_duplicate_case_insensitive_rejected(self):
        root = _subject()
        _topic(root, "Puzzles")
        with pytest.raises(ContentError) as e:
            svc.create_node(institution_id=INSTITUTION_A, actor_id=ACTOR, name="PUZZLES", parent_id=root.id)
        assert e.value.code == "duplicate_name" and e.value.status == 409

    def test_root_duplicate_rejected_even_though_db_constraint_skips_nulls(self):
        _subject("Reasoning")
        with pytest.raises(ContentError) as e:
            svc.create_node(institution_id=INSTITUTION_A, actor_id=ACTOR, name="reasoning")
        assert e.value.code == "duplicate_name"

    def test_same_name_under_different_parents_allowed(self):
        _topic(_subject("A"), "Puzzles")
        _topic(_subject("B"), "Puzzles")

    def test_blank_name_rejected(self):
        with pytest.raises(ContentError) as e:
            svc.create_node(institution_id=INSTITUTION_A, actor_id=ACTOR, name="   ")
        assert e.value.code == "validation_error"

    def test_name_over_max_rejected(self):
        with pytest.raises(ContentError) as e:
            svc.create_node(institution_id=INSTITUTION_A, actor_id=ACTOR, name="x" * 201)
        assert e.value.code == "validation_error"

    def test_cannot_add_under_retired_node(self):
        root = _subject()
        svc.retire_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=root.id)
        with pytest.raises(ContentError) as e:
            svc.create_node(institution_id=INSTITUTION_A, actor_id=ACTOR, name="Child", parent_id=root.id)
        assert e.value.code == "node_retired"

    def test_publish_is_idempotent(self):
        n = _subject(publish=False)
        svc.publish_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=n.id)
        svc.publish_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=n.id)
        assert ContentNode.objects.get(pk=n.id).status == NODE_PUBLISHED

    def test_retire_then_publish_refused_restore_required(self):
        n = _subject()
        svc.retire_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=n.id)
        with pytest.raises(ContentError) as e:
            svc.publish_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=n.id)
        assert e.value.code == "invalid_transition"

    def test_restore_refused_when_parent_retired(self):
        root = _subject()
        child = _topic(root)
        svc.retire_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=child.id)
        svc.retire_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=root.id)
        with pytest.raises(ContentError) as e:
            svc.restore_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=child.id)
        assert e.value.code == "invalid_transition"

    def test_delete_node_blocked_when_it_has_children_or_questions(self):
        root = _subject()
        topic = _topic(root)
        _question(topic)
        with pytest.raises(ContentError) as e:
            svc.delete_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=root.id)
        assert e.value.code == "node_not_empty"
        with pytest.raises(ContentError) as e:
            svc.delete_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id)
        assert e.value.code == "node_not_empty"

    def test_delete_empty_node_allowed(self):
        n = _subject()
        svc.delete_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=n.id)
        assert not ContentNode.objects.filter(pk=n.id).exists()

    def test_other_institution_cannot_see_node(self):
        n = _subject()
        with pytest.raises(ContentError) as e:
            svc.get_node(INSTITUTION_B, n.id)
        assert e.value.status == 404


# ── question creation and draft editing ─────────────────────────────────────

@pytest.mark.django_db
class TestQuestionCreate:
    def test_create_gives_draft_question_with_version_one_and_options(self, topic):
        q, v = _question(topic)
        assert q.status == QUESTION_DRAFT and q.current_version_no == 1
        assert v.state == VERSION_DRAFT and v.version_no == 1
        assert v.options.count() == 4
        assert [o.label for o in v.options.order_by("display_order")] == ["A", "B", "C", "D"]

    def test_question_directly_under_subject_refused(self):
        root = _subject()
        with pytest.raises(ContentError) as e:
            svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=root.id, text="Q?", options=OK_OPTIONS)
        assert e.value.code == "invalid_parent"

    def test_create_under_retired_topic_refused(self):
        root = _subject()
        t = _topic(root)
        svc.retire_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=t.id)
        with pytest.raises(ContentError) as e:
            svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=t.id, text="Q?", options=OK_OPTIONS)
        assert e.value.code == "node_retired"

    def test_empty_text_refused_at_create(self, topic):
        with pytest.raises(ContentError) as e:
            svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="  ", options=OK_OPTIONS)
        assert e.value.code == "validation_error"

    def test_text_at_max_accepted_and_one_over_refused(self, topic):
        svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="a" * 2000, options=OK_OPTIONS)
        with pytest.raises(ContentError) as e:
            svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="a" * 2001, options=OK_OPTIONS)
        assert e.value.code == "validation_error"

    def test_display_order_increments(self, topic):
        q1, _ = _question(topic, "one?")
        q2, _ = _question(topic, "two?")
        assert (q1.display_order, q2.display_order) == (1, 2)

    def test_image_without_alt_text_refused_at_save(self, topic):
        with pytest.raises(ContentError) as e:
            svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="Q?",
                                options=OK_OPTIONS, image_key="uploads/content/x.png", image_alt_text="")
        assert "image_alt_text" in e.value.errors


@pytest.mark.django_db
class TestDraftEditing:
    def test_edit_draft_with_matching_etag(self, topic):
        q, v = _question(topic)
        svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                         if_match=_etag(q), changes={"text": "Changed?"})
        assert ContentQuestionVersion.objects.get(pk=v.id).question_text == "Changed?"

    def test_missing_if_match_is_428(self, topic):
        q, _ = _question(topic)
        with pytest.raises(ContentError) as e:
            svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                             if_match="", changes={"text": "x?"})
        assert e.value.status == 428 and e.value.code == "precondition_required"

    def test_stale_etag_is_412_and_returns_current(self, topic):
        q, _ = _question(topic)
        stale = _etag(q)
        svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                         if_match=stale, changes={"text": "first?"})
        with pytest.raises(ContentError) as e:
            svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                             if_match=stale, changes={"text": "second?"})
        assert e.value.status == 412 and "current_etag" in e.value.errors

    def test_edit_replacing_options_with_two_correct_saves_as_draft_but_publish_refuses(self, topic):
        # Draft saves allow partial/invalid content (section 2.5); publish does not.
        q, _ = _question(topic)
        bad = [{"option_text": "A", "is_correct": True}, {"option_text": "B", "is_correct": True}]
        svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                         if_match=_etag(q), changes={"options": bad})
        with pytest.raises(ContentError) as e:
            svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        assert e.value.code == "validation_error" and "options" in e.value.errors


# ── options rules ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestOptionRules:
    def _publish_with(self, topic, options, text="Q?"):
        q, _ = svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id,
                                   text=text, options=options)
        q = ContentQuestion.objects.get(pk=q.id)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        return q

    def test_one_option_refused_at_publish(self, topic):
        q, _ = svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id,
                                   text="Q?", options=[{"option_text": "A", "is_correct": True}])
        q = ContentQuestion.objects.get(pk=q.id)
        with pytest.raises(ContentError) as e:
            svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        assert e.value.code == "validation_error"

    def test_seven_options_refused_at_draft_save(self, topic):
        seven = [{"option_text": f"o{i}", "is_correct": i == 0} for i in range(7)]
        with pytest.raises(ContentError) as e:
            svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="Q?", options=seven)
        assert e.value.code == "validation_error"

    def test_min_and_max_option_counts_accepted(self, topic):
        self._publish_with(topic, [{"option_text": "A", "is_correct": True}, {"option_text": "B", "is_correct": False}])
        six = [{"option_text": f"o{i}", "is_correct": i == 0} for i in range(6)]
        self._publish_with(topic, six, text="Six?")

    def test_zero_correct_refused_at_publish(self, topic):
        q, _ = svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="Q?",
                                   options=[{"option_text": "A", "is_correct": False}, {"option_text": "B", "is_correct": False}])
        q = ContentQuestion.objects.get(pk=q.id)
        with pytest.raises(ContentError) as e:
            svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        assert e.value.code == "validation_error"

    def test_duplicate_options_refused(self, topic):
        dup = [{"option_text": "Same", "is_correct": True}, {"option_text": " same ", "is_correct": False}]
        with pytest.raises(ContentError) as e:
            svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="Q?", options=dup)
        assert e.value.code == "validation_error"


# ── review and publish ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReviewAndPublish:
    def test_submit_then_withdraw(self, topic):
        q, _ = _question(topic)
        svc.submit_review(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        q = ContentQuestion.objects.get(pk=q.id)
        assert svc.open_version(q).state == VERSION_IN_REVIEW
        svc.withdraw_review(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        assert svc.open_version(ContentQuestion.objects.get(pk=q.id)).state == VERSION_DRAFT

    def test_edit_refused_while_in_review(self, topic):
        q, _ = _question(topic)
        svc.submit_review(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        q = ContentQuestion.objects.get(pk=q.id)
        with pytest.raises(ContentError) as e:
            svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                             if_match=_etag(q), changes={"text": "x?"})
        assert e.value.code == "invalid_transition"

    def test_publish_freezes_and_sets_status(self, topic):
        q, v = _question(topic)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        q = ContentQuestion.objects.get(pk=q.id)
        assert q.status == QUESTION_PUBLISHED and q.published_version_no == 1
        assert ContentQuestionVersion.objects.get(pk=v.id).state == VERSION_PUBLISHED

    def test_publish_is_idempotent_on_repeat(self, topic):
        q, _ = _question(topic)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        q = ContentQuestion.objects.get(pk=q.id)
        _, v = svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match="")
        assert v.state == VERSION_PUBLISHED

    def test_publish_refused_when_topic_unpublished(self):
        root = _subject()
        t = _topic(root, publish=False)
        q, _ = svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=t.id, text="Q?", options=OK_OPTIONS)
        q = ContentQuestion.objects.get(pk=q.id)
        with pytest.raises(ContentError) as e:
            svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        assert e.value.code == "invalid_transition"

    def test_publish_refused_when_question_retired(self, topic):
        q, _ = _question(topic)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        svc.retire_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        q = ContentQuestion.objects.get(pk=q.id)
        with pytest.raises(ContentError) as e:
            svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match="\"x\"")
        assert e.value.code == "invalid_transition"


# ── versioning ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestVersioning:
    def _published(self, topic, text="Original?"):
        q, _ = _question(topic, text)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        return ContentQuestion.objects.get(pk=q.id)

    def test_edit_published_clones_new_draft_and_keeps_published_unchanged(self, topic):
        q = self._published(topic)
        published = svc.latest_published(q)
        svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                         if_match=svc.etag_for(published), changes={"text": "Edited?"})
        q = ContentQuestion.objects.get(pk=q.id)
        assert q.current_version_no == 2 and q.published_version_no == 1
        assert ContentQuestionVersion.objects.get(question=q, version_no=1).question_text == "Original?"
        assert ContentQuestionVersion.objects.get(question=q, version_no=2).question_text == "Edited?"

    def test_published_version_cannot_be_edited_directly(self, topic):
        q = self._published(topic)
        published = svc.latest_published(q)
        # Any write must go through a draft; the published row is never the write target.
        svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                         if_match=svc.etag_for(published), changes={"text": "New?"})
        assert ContentQuestionVersion.objects.get(pk=published.pk).question_text == "Original?"

    def test_version_numbers_never_reused_after_discard(self, topic):
        q = self._published(topic)
        published = svc.latest_published(q)
        svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                         if_match=svc.etag_for(published), changes={"text": "Draft?"})
        q = ContentQuestion.objects.get(pk=q.id)
        svc.discard_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                          if_match=_etag(q))
        q = ContentQuestion.objects.get(pk=q.id)
        assert q.current_version_no == 2  # 2 was used; the next draft becomes 3, not 2
        svc.update_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                         if_match=svc.etag_for(svc.latest_published(q)), changes={"text": "Next?"})
        assert ContentQuestion.objects.get(pk=q.id).current_version_no == 3

    def test_discard_only_version_refused(self, topic):
        q, _ = _question(topic)
        with pytest.raises(ContentError) as e:
            svc.discard_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        assert e.value.code == "cannot_discard_only_version"

    def test_discard_without_draft_refused(self, topic):
        q = self._published(topic)
        with pytest.raises(ContentError) as e:
            svc.discard_draft(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match="\"x\"")
        assert e.value.code == "invalid_transition"


# ── retire, restore, delete ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestRetireRestoreDelete:
    def _published(self, topic):
        q, _ = _question(topic)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        return ContentQuestion.objects.get(pk=q.id)

    def test_retire_only_from_published(self, topic):
        q, _ = _question(topic)
        with pytest.raises(ContentError) as e:
            svc.retire_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert e.value.code == "invalid_transition"

    def test_retire_then_restore_roundtrip(self, topic):
        q = self._published(topic)
        svc.retire_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert ContentQuestion.objects.get(pk=q.id).status == QUESTION_RETIRED
        svc.restore_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert ContentQuestion.objects.get(pk=q.id).status == QUESTION_PUBLISHED

    def test_restore_refused_when_topic_retired(self, topic):
        q = self._published(topic)
        svc.retire_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        svc.retire_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id)
        with pytest.raises(ContentError) as e:
            svc.restore_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert e.value.code == "invalid_transition"

    def test_delete_draft_question_allowed(self, topic):
        q, _ = _question(topic)
        with patch("content.media._delete_object"):
            svc.delete_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert not ContentQuestion.objects.filter(pk=q.id).exists()
        assert not ContentQuestionVersion.objects.filter(question_id=q.id).exists()

    def test_delete_published_unused_allowed(self, topic):
        q = self._published(topic)
        with patch("content.media._delete_object"):
            svc.delete_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert not ContentQuestion.objects.filter(pk=q.id).exists()

    def test_delete_used_question_refused_with_retire_message(self, topic):
        q = self._published(topic)
        ContentQuestionUsage.objects.create(question=q, version_no=1, usage_type="generated_paper", usage_ref_id=uuid.uuid4())
        with pytest.raises(ContentError) as e:
            svc.delete_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert e.value.code == "used_question" and "retire" in e.value.message
        assert ContentQuestion.objects.filter(pk=q.id).exists()

    def test_delete_renumbers_remaining_questions(self, topic):
        q1, _ = _question(topic, "one?")
        q2, _ = _question(topic, "two?")
        q3, _ = _question(topic, "three?")
        svc.delete_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q2.id)
        orders = list(ContentQuestion.objects.filter(node=topic).order_by("display_order").values_list("display_order", flat=True))
        assert orders == [1, 2]

    def test_one_hundred_minus_five_renumbers_to_ninety_five(self, topic):
        qs = [_question(topic, f"q{i}?")[0] for i in range(100)]
        for q in qs[50:55]:
            svc.delete_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        orders = list(ContentQuestion.objects.filter(node=topic).order_by("display_order").values_list("display_order", flat=True))
        assert orders == list(range(1, 96))


# ── reorder ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReorder:
    def test_reorder_with_full_set(self, topic):
        a, _ = _question(topic, "a?")
        b, _ = _question(topic, "b?")
        svc.reorder_questions(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id,
                              ordered_ids=[str(b.id), str(a.id)])
        assert ContentQuestion.objects.get(pk=b.id).display_order == 1
        assert ContentQuestion.objects.get(pk=a.id).display_order == 2

    def test_reorder_with_missing_id_refused(self, topic):
        a, _ = _question(topic, "a?")
        _question(topic, "b?")
        with pytest.raises(ContentError) as e:
            svc.reorder_questions(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, ordered_ids=[str(a.id)])
        assert e.value.code == "set_mismatch"

    def test_reorder_with_duplicate_id_refused(self, topic):
        a, _ = _question(topic, "a?")
        _question(topic, "b?")
        with pytest.raises(ContentError) as e:
            svc.reorder_questions(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id,
                                  ordered_ids=[str(a.id), str(a.id)])
        assert e.value.code == "set_mismatch"


# ── eligibility (Part 2 contract) ──────────────────────────────────────────

@pytest.mark.django_db
class TestEligibility:
    def test_published_question_under_published_chain_is_eligible(self):
        root = _subject()
        t = _topic(root)
        q, _ = _question(t)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        assert svc.is_eligible(ContentQuestion.objects.get(pk=q.id))

    def test_draft_question_not_eligible(self, topic):
        q, _ = _question(topic)
        assert not svc.is_eligible(q)

    def test_retiring_ancestor_makes_descendants_ineligible_without_changing_their_status(self):
        root = _subject()
        t = _topic(root)
        q, _ = _question(t)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        svc.retire_node(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=root.id)
        q = ContentQuestion.objects.get(pk=q.id)
        assert q.status == QUESTION_PUBLISHED
        assert not svc.is_eligible(q)


# ── audit ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAudit:
    def test_each_write_writes_audit_row_with_actor_and_request(self, topic):
        q, _ = _question(topic)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id,
                             if_match=_etag(q), request_id="req-123")
        row = ContentAuditEvent.objects.filter(action="question.publish").get()
        assert row.actor_id == ACTOR and row.request_id == "req-123" and row.institution_id == INSTITUTION_A

    def test_audit_summaries_never_contain_question_or_option_text(self, topic):
        secret = "SECRET-ANSWER-TEXT-9731"
        q, _ = svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id,
                                   text=f"Question {secret}?",
                                   options=[{"option_text": f"opt {secret}", "is_correct": True},
                                            {"option_text": "other", "is_correct": False}])
        q = ContentQuestion.objects.get(pk=q.id)
        svc.publish_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id, if_match=_etag(q))
        for row in ContentAuditEvent.objects.all():
            assert secret not in str(row.summary)

    def test_audit_rows_survive_question_delete(self, topic):
        q, _ = _question(topic)
        svc.delete_question(institution_id=INSTITUTION_A, actor_id=ACTOR, question_id=q.id)
        assert ContentAuditEvent.objects.filter(entity_id=q.id, action="question.delete").exists()


# ── media release on delete (orphan ledger path) ───────────────────────────

@pytest.mark.django_db
class TestMediaRelease:
    def test_delete_question_with_image_schedules_release_after_commit(self, topic):
        from django.test import TransactionTestCase  # noqa: F401  (on_commit needs a real commit)
        q, _ = svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=topic.id, text="Q?",
                                   options=OK_OPTIONS, image_key="uploads/content/abc.png", image_alt_text="a chart")
        with patch("content.services.release_keys_after_commit") as release:
            svc.delete_question(institution_id=INSTITUTION_A, actor_id=ACTOR,
                                question_id=ContentQuestion.objects.get(pk=q.id).id)
        release.assert_called_once()
        assert "uploads/content/abc.png" in release.call_args.args[0]


@pytest.mark.django_db
class TestNodeReorder:
    def test_reorder_root_subjects(self):
        a = _subject("Alpha")
        b = _subject("Beta")
        svc.reorder_nodes(institution_id=INSTITUTION_A, actor_id=ACTOR, parent_id=None,
                          ordered_ids=[str(b.id), str(a.id)])
        assert ContentNode.objects.get(pk=b.id).display_order == 1
        assert ContentNode.objects.get(pk=a.id).display_order == 2

    def test_reorder_missing_sibling_refused(self):
        a = _subject("Alpha")
        _subject("Beta")
        with pytest.raises(ContentError) as e:
            svc.reorder_nodes(institution_id=INSTITUTION_A, actor_id=ACTOR, parent_id=None, ordered_ids=[str(a.id)])
        assert e.value.code == "set_mismatch"
