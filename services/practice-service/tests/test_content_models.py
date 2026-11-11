import importlib
import uuid

import pytest
from django.db import IntegrityError, transaction

from content.models import (
    ContentNode, ContentQuestion, ContentQuestionVersion, ContentOption,
    NODE_DRAFT, QUESTION_DRAFT, VERSION_DRAFT, VERSION_PUBLISHED, VERSION_IN_REVIEW,
)
from tests.conftest import INSTITUTION_A, ADMIN_USER_ID


def _node(name="Reasoning", parent=None, institution=INSTITUTION_A):
    return ContentNode.objects.create(
        institution_id=institution, parent=parent, name=name,
        created_by=ADMIN_USER_ID, updated_by=ADMIN_USER_ID,
    )


def _question(node):
    return ContentQuestion.objects.create(
        institution_id=node.institution_id, node=node,
        created_by=ADMIN_USER_ID, updated_by=ADMIN_USER_ID,
    )


def _version(question, version_no=1, state=VERSION_DRAFT):
    return ContentQuestionVersion.objects.create(
        question=question, version_no=version_no, state=state, question_text="Q?",
        created_by=ADMIN_USER_ID, updated_by=ADMIN_USER_ID,
    )


@pytest.mark.django_db
class TestMigrationIsolation:
    """B3: the content migration only creates content_* objects."""

    def test_migration_touches_only_content_objects(self):
        migration = importlib.import_module("content.migrations.0001_initial")
        names = []
        for op in migration.Migration.operations:
            name = getattr(op, "name", None) or getattr(op, "model_name", None) or ""
            names.append(name)
            assert type(op).__name__ in {"CreateModel", "AddIndex", "AddConstraint"}, type(op).__name__
        assert names and all(n.lower().startswith("content") for n in names)

    def test_content_tables_use_content_prefix(self):
        from content.models import (
            ContentNode, ContentQuestion, ContentQuestionVersion, ContentOption,
            ContentQuestionUsage, ContentAuditEvent, ContentMediaOrphan,
        )
        tables = [m._meta.db_table for m in (
            ContentNode, ContentQuestion, ContentQuestionVersion, ContentOption,
            ContentQuestionUsage, ContentAuditEvent, ContentMediaOrphan,
        )]
        assert all(t.startswith("content_") for t in tables)


@pytest.mark.django_db
class TestNodeConstraints:
    def test_duplicate_child_name_case_insensitive_rejected(self):
        root = _node("Reasoning", parent=None)
        _node("Puzzles", parent=root)
        with pytest.raises(IntegrityError), transaction.atomic():
            _node("PUZZLES", parent=root)

    def test_same_name_under_different_parents_allowed(self):
        a = _node("A")
        b = _node("B")
        _node("Puzzles", parent=a)
        _node("Puzzles", parent=b)
        assert ContentNode.objects.filter(name="Puzzles").count() == 2

    def test_new_node_defaults_to_draft(self):
        assert _node().status == NODE_DRAFT


@pytest.mark.django_db
class TestVersionConstraints:
    def test_second_open_version_rejected(self):
        q = _question(_node("Topic", parent=_node("Subject")))
        _version(q, 1, VERSION_DRAFT)
        with pytest.raises(IntegrityError), transaction.atomic():
            _version(q, 2, VERSION_IN_REVIEW)

    def test_published_plus_new_draft_allowed(self):
        q = _question(_node("Topic", parent=_node("Subject")))
        _version(q, 1, VERSION_PUBLISHED)
        _version(q, 2, VERSION_DRAFT)
        assert q.versions.count() == 2

    def test_duplicate_version_number_rejected(self):
        q = _question(_node("Topic", parent=_node("Subject")))
        _version(q, 1, VERSION_PUBLISHED)
        with pytest.raises(IntegrityError), transaction.atomic():
            _version(q, 1, VERSION_DRAFT)

    def test_version_ids_are_unique_uuids(self):
        q = _question(_node("Topic", parent=_node("Subject")))
        v = _version(q)
        assert isinstance(v.id, uuid.UUID)


@pytest.mark.django_db
class TestOptionStorage:
    def test_options_attach_to_version(self):
        q = _question(_node("Topic", parent=_node("Subject")))
        v = _version(q)
        ContentOption.objects.create(version=v, label="A", option_text="x", is_correct=True, display_order=1)
        ContentOption.objects.create(version=v, label="B", option_text="y", is_correct=False, display_order=2)
        assert v.options.count() == 2
