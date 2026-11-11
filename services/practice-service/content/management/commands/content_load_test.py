"""Load check for the content bank (LIVETRACKER4 section 2.16, task H5).

Seeds one topic with N published questions, then runs W concurrent admin workers
mixing reads and draft writes. Reports latency percentiles and error counts.

Two modes:
- default: in-process Django test client (no HTTP, shares one interpreter; useful for
  query and logic checks, NOT valid for concurrency SLOs because threads share the GIL).
- --base-url URL: real HTTP requests to a running server (gunicorn), the mode used for
  SLO evidence. The server must use the same database and the same JWT signing key.

Run only against a non-production database.
"""
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from content.models import ContentNode, ContentQuestion, ContentQuestionVersion, ContentOption

BASE = "/api/practice/content"


class _User:
    pk = None
    id = None


def _token(user_id, institution_id):
    _User.pk = _User.id = user_id
    refresh = RefreshToken.for_user(_User())
    refresh["role"] = "admin"
    refresh["email"] = "load@test.local"
    refresh["institution_id"] = str(institution_id)
    refresh["student_id"] = None
    refresh["is_profile_completed"] = False
    return str(refresh.access_token)


def _percentile(samples, pct):
    if not samples:
        return 0.0
    ordered = sorted(samples)
    k = max(0, min(len(ordered) - 1, int(round(pct / 100 * len(ordered))) - 1))
    return ordered[k]


def _client_send(method, url, token, body=None, etag=None):
    """In-process request. Returns (status, ETag header)."""
    client = Client()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    if etag:
        headers["HTTP_IF_MATCH"] = etag
    if method == "GET":
        r = client.get(url, **headers)
    else:
        r = client.patch(url, body, content_type="application/json", **headers)
    return r.status_code, r.headers.get("ETag", "")


def _http_send(base_url):
    """Real HTTP request with the standard library (no extra dependency). Returns (status, ETag)."""
    def send(method, url, token, body=None, etag=None):
        headers = {"Authorization": f"Bearer {token}"}
        if etag:
            headers["If-Match"] = etag
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(base_url + url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, resp.headers.get("ETag", "")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("ETag", "") if exc.headers else ""
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, ""
    return send


class Command(BaseCommand):
    help = "Seed questions and run concurrent admin workers against the content API."

    def add_arguments(self, parser):
        parser.add_argument("--questions", type=int, default=2000)
        parser.add_argument("--workers", type=int, default=50)
        parser.add_argument("--requests-per-worker", type=int, default=20)
        parser.add_argument("--base-url", default="", help="Real server URL, e.g. http://content-load-server:8000")

    def handle(self, *args, **opts):
        settings.CONTENT_BANK_ENABLED = True
        # Django's Client sends Host: testserver. The test runner adds that host to
        # ALLOWED_HOSTS, but this command runs under manage.py, so add it here.
        settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]
        institution = uuid.uuid4()
        admin = uuid.uuid4()
        root = ContentNode.objects.create(institution_id=institution, name="Load", created_by=admin, updated_by=admin, status="published")
        topic = ContentNode.objects.create(institution_id=institution, parent=root, name="Topic", created_by=admin, updated_by=admin, status="published")
        n = opts["questions"]
        questions = [ContentQuestion(institution_id=institution, node=topic, display_order=i + 1, status="published",
                                     current_version_no=1, published_version_no=1, created_by=admin, updated_by=admin)
                     for i in range(n)]
        ContentQuestion.objects.bulk_create(questions, batch_size=500)
        qids = list(ContentQuestion.objects.filter(node=topic).order_by("display_order").values_list("id", flat=True))
        versions = [ContentQuestionVersion(question_id=qid, version_no=1, state="published", question_text=f"Question {i}?",
                                           created_by=admin, updated_by=admin, published_by=admin)
                    for i, qid in enumerate(qids)]
        ContentQuestionVersion.objects.bulk_create(versions, batch_size=500)
        vids = list(ContentQuestionVersion.objects.filter(question_id__in=qids).values_list("id", "question_id"))
        options = []
        for vid, _qid in vids:
            options += [ContentOption(version_id=vid, label=c, option_text=f"opt {c}", is_correct=(c == "A"),
                                      display_order=i + 1) for i, c in enumerate("ABCD")]
        ContentOption.objects.bulk_create(options, batch_size=2000)
        self.stdout.write(f"seeded {n} published questions under one topic")

        base_url = opts["base_url"].rstrip("/")
        send = _http_send(base_url) if base_url else _client_send
        mode = f"http {base_url}" if base_url else "in-process"
        latencies = {"list": [], "detail": [], "write": []}
        errors = []
        lock = threading.Lock()
        per_worker = opts["requests_per_worker"]
        node_id = str(topic.id)

        def worker(index):
            try:
                for step in range(per_worker):
                    # Fresh token per request: SimpleJWT access tokens expire after 5 minutes,
                    # which made a long run fail with 401 (first run, LIVETRACKER4 H5).
                    token = _token(admin, institution)
                    qid = str(qids[(index * per_worker + step) % len(qids)])
                    if step % 3 == 0:
                        kind, url = "list", f"{BASE}/questions/?node_id={node_id}&page={1 + step % 5}"
                        t0 = time.perf_counter()
                        status, _ = send("GET", url, token)
                    elif step % 3 == 1:
                        kind, url = "detail", f"{BASE}/questions/{qid}/"
                        t0 = time.perf_counter()
                        status, _ = send("GET", url, token)
                    else:
                        kind, url = "write", f"{BASE}/questions/{qid}/"
                        _, etag = send("GET", url, token)
                        t0 = time.perf_counter()
                        status, _ = send("PATCH", url, token, body={"text": f"Edited {index}-{step}?"}, etag=etag)
                    elapsed = (time.perf_counter() - t0) * 1000
                    with lock:
                        latencies[kind].append(elapsed)
                        if status == 0 or status >= 500 or (kind == "write" and status not in (200, 412)):
                            errors.append((kind, status))
            finally:
                connections.close_all()

        started = time.perf_counter()
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(opts["workers"])]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.perf_counter() - started

        total = sum(len(v) for v in latencies.values())
        self.stdout.write(f"mode={mode} requests={total} workers={opts['workers']} wall_seconds={wall:.1f} "
                          f"rps={total / wall:.1f} errors={len(errors)}")
        for kind, samples in latencies.items():
            if samples:
                self.stdout.write(f"{kind}: n={len(samples)} p50={statistics.median(samples):.0f}ms "
                                  f"p95={_percentile(samples, 95):.0f}ms max={max(samples):.0f}ms")
        targets = {"list": 300, "detail": 300, "write": 500}
        breaches = [k for k, t in targets.items() if latencies[k] and _percentile(latencies[k], 95) > t]
        self.stdout.write("SLO: " + ("met" if not breaches and not errors else f"breached {breaches} errors={len(errors)}"))
