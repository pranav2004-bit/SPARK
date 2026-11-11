from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from content.models import ContentMediaOrphan, ContentQuestionVersion
from tests.test_content_services import ACTOR, OK_OPTIONS, _subject, _topic
from tests.conftest import INSTITUTION_A
from content import services as svc


@pytest.mark.django_db
class TestOrphanCleanup:
    def _orphan(self, key):
        return ContentMediaOrphan.objects.create(key=key, reason="s3_delete_failed")

    def test_dry_run_deletes_nothing(self):
        self._orphan("uploads/content/a.png")
        out = StringIO()
        with patch("content.management.commands.content_cleanup_orphans._delete_object") as d:
            call_command("content_cleanup_orphans", stdout=out)
        d.assert_not_called()
        assert ContentMediaOrphan.objects.get().cleaned_at is None
        assert "would delete" in out.getvalue()

    def test_apply_deletes_and_marks_cleaned(self):
        self._orphan("uploads/content/b.png")
        with patch("content.management.commands.content_cleanup_orphans._delete_object") as d:
            call_command("content_cleanup_orphans", "--apply", stdout=StringIO())
        d.assert_called_once_with("uploads/content/b.png")
        assert ContentMediaOrphan.objects.get().cleaned_at is not None

    def test_referenced_key_is_never_deleted(self):
        root = _subject()
        t = _topic(root)
        q, v = svc.create_question(institution_id=INSTITUTION_A, actor_id=ACTOR, node_id=t.id, text="Q?",
                                   options=OK_OPTIONS, image_key="uploads/content/keep.png", image_alt_text="x")
        self._orphan("uploads/content/keep.png")
        with patch("content.management.commands.content_cleanup_orphans._delete_object") as d:
            call_command("content_cleanup_orphans", "--apply", stdout=StringIO())
        d.assert_not_called()
        assert ContentQuestionVersion.objects.filter(image_key="uploads/content/keep.png").exists()

    def test_failed_delete_stays_pending_for_next_run(self):
        self._orphan("uploads/content/c.png")
        with patch("content.management.commands.content_cleanup_orphans._delete_object", side_effect=RuntimeError("s3")):
            call_command("content_cleanup_orphans", "--apply", stdout=StringIO(), stderr=StringIO())
        assert ContentMediaOrphan.objects.get().cleaned_at is None
