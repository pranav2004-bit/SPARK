import threading

from django.db import connections

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from tests.conftest import ADMIN_USER_ID, INSTITUTION_A, _make_token
from tests.test_content_api import BASE, OPTS, _create_subject, _create_topic, _publish_node


from django.conf import settings as _settings

REQUIRES_POSTGRES = "postgresql" not in _settings.DATABASES["default"]["ENGINE"]


@pytest.mark.skipif(REQUIRES_POSTGRES, reason="row locks need PostgreSQL; run with core.test_settings_pg")
@pytest.mark.django_db(transaction=True)
class TestConcurrentWriters:
    """LIVETRACKER4 section 2.8 / H2: two writers, same If-Match. Exactly one may win."""

    def test_two_concurrent_patches_one_wins_one_gets_412(self):
        with override_settings(CONTENT_BANK_ENABLED=True):
            token = _make_token(ADMIN_USER_ID, "admin", INSTITUTION_A)

            def client():
                c = APIClient()
                c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                return c

            admin = client()
            subject = _create_subject(admin)
            _publish_node(admin, subject)
            topic = _create_topic(admin, subject)
            _publish_node(admin, topic)
            created = admin.post(f"{BASE}/questions/", {"node_id": topic, "text": "Q?", "options": OPTS},
                                 format="json")
            qid, etag = created.json()["data"]["id"], created.headers["ETag"]

            barrier = threading.Barrier(2)
            statuses = []
            lock = threading.Lock()

            def writer(label):
                try:
                    c = client()
                    barrier.wait()
                    r = c.patch(f"{BASE}/questions/{qid}/", {"text": f"from {label}?"}, format="json",
                                HTTP_IF_MATCH=etag)
                    with lock:
                        statuses.append(r.status_code)
                finally:
                    connections.close_all()

            threads = [threading.Thread(target=writer, args=(n,)) for n in ("a", "b")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert sorted(statuses) == [200, 412]


def _race(fn, labels):
    """Run fn(label) in threads released together; return the list of results."""
    barrier = threading.Barrier(len(labels))
    results = []
    lock = threading.Lock()

    def runner(label):
        try:
            barrier.wait()
            value = fn(label)
            with lock:
                results.append(value)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=runner, args=(label,)) for label in labels]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@pytest.mark.skipif(REQUIRES_POSTGRES, reason="row locks need PostgreSQL; run with core.test_settings_pg")
@pytest.mark.django_db(transaction=True)
class TestConcurrentPublishAndReorder:
    """LIVETRACKER4 section 2.13 / H2: concurrent publish (one transition) and concurrent reorder."""

    def _setup(self):
        token = _make_token(ADMIN_USER_ID, "admin", INSTITUTION_A)

        def client():
            c = APIClient()
            c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            return c

        admin = client()
        subject = _create_subject(admin)
        _publish_node(admin, subject)
        topic = _create_topic(admin, subject)
        _publish_node(admin, topic)
        return client, admin, topic

    def test_two_concurrent_publishes_make_one_state_change(self):
        from content.models import ContentAuditEvent
        with override_settings(CONTENT_BANK_ENABLED=True):
            client, admin, topic = self._setup()
            created = admin.post(f"{BASE}/questions/", {"node_id": topic, "text": "Q?", "options": OPTS},
                                 format="json")
            qid, etag = created.json()["data"]["id"], created.headers["ETag"]

            def publish(_label):
                return client().post(f"{BASE}/questions/{qid}/publish/", format="json",
                                     HTTP_IF_MATCH=etag).status_code

            statuses = _race(publish, ["a", "b"])
            publishes = ContentAuditEvent.objects.filter(entity_id=qid, action="question.publish").count()
            assert sorted(statuses) == [200, 200]
            assert publishes == 1

    def test_concurrent_reorders_leave_one_complete_order(self):
        with override_settings(CONTENT_BANK_ENABLED=True):
            client, admin, topic = self._setup()
            for text in ("Q1?", "Q2?", "Q3?"):
                admin.post(f"{BASE}/questions/", {"node_id": topic, "text": text, "options": OPTS}, format="json")
            listing = admin.get(f"{BASE}/questions/?node_id={topic}").json()["results"]
            ids = [row["id"] for row in listing]
            order_a = ids
            order_b = list(reversed(ids))

            def reorder(label):
                order = order_a if label == "a" else order_b
                return client().post(f"{BASE}/questions/reorder/", {"node_id": topic, "question_ids": order},
                                     format="json").status_code

            statuses = _race(reorder, ["a", "b"])
            final = [row["id"] for row in admin.get(f"{BASE}/questions/?node_id={topic}").json()["results"]]
            assert all(s == 200 for s in statuses)
            assert final in (order_a, order_b)
