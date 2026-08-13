from django.core.cache import cache
from django.db.models import Count, Avg, Sum, Q
from rest_framework.views import APIView
from rest_framework import status

from core.permissions import IsStudentUser, IsAdminUser, IsSuperAdminUser, IsServiceKey
from core.responses import success_response, error_response
from .models import PracticeEvent, ResourceViewEvent, DailyEngagementSnapshot, InstitutionSnapshot
from .serializers import InternalEventSerializer

_ADMIN_CACHE_TTL = 900       # 15 minutes
_SUPERADMIN_CACHE_TTL = 1800  # 30 minutes
_STUDENT_CACHE_TTL = 300      # 5 minutes


def _admin_overview_key(institution_id):
    return f"analytics:admin:{institution_id}:overview"


def _superadmin_overview_key():
    return "analytics:superadmin:overview"


def _student_key(institution_id, student_id):
    return f"analytics:student:{institution_id}:{student_id}"


def _invalidate_student_cache(institution_id, student_id):
    cache.delete(_student_key(institution_id, student_id))


def _invalidate_admin_cache(institution_id):
    cache.delete(_admin_overview_key(institution_id))


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = []  # never throttle — polled at high frequency by health checks

    def get(self, request):
        from django.db import connection
        try:
            connection.ensure_connection()
            db_status = "ok"
        except Exception:
            db_status = "error"
        return success_response(data={"service": "analytics-service", "status": "ok", "db": db_status})


class StudentAnalyticsView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request):
        student_id = request.user.id
        institution_id = getattr(request.user, "institution_id", None)
        key = _student_key(institution_id, student_id)
        cached = cache.get(key)
        if cached is not None:
            return success_response(data=cached)

        events = PracticeEvent.objects.filter(student_id=student_id, institution_id=institution_id)
        total = events.count()
        correct = events.filter(is_correct=True).count()

        accuracy = round((correct / total * 100), 2) if total > 0 else 0.0

        # Topic breakdown
        topic_stats = (
            events.values("topic")
            .annotate(attempts=Count("id"), correct=Count("id", filter=Q(is_correct=True)))
            .order_by("-attempts")
        )
        topic_breakdown = [
            {
                "topic": t["topic"] or "Unknown",
                "attempts": t["attempts"],
                "correct": t["correct"],
                "accuracy": round(t["correct"] / t["attempts"] * 100, 2) if t["attempts"] > 0 else 0.0,
            }
            for t in topic_stats
        ]

        strong_topics = sorted(
            [t for t in topic_breakdown if t["attempts"] >= 3],
            key=lambda x: -x["accuracy"]
        )[:5]
        weak_topics = sorted(
            [t for t in topic_breakdown if t["attempts"] >= 3],
            key=lambda x: x["accuracy"]
        )[:5]

        # Streak: consecutive days with at least one attempt
        streak = _compute_streak(student_id, institution_id)

        data = {
            "total_attempts": total,
            "correct_attempts": correct,
            "accuracy_percent": accuracy,
            "topic_breakdown": topic_breakdown,
            "strong_topics": strong_topics,
            "weak_topics": weak_topics,
            "practice_streak_days": streak,
        }
        cache.set(key, data, _STUDENT_CACHE_TTL)
        return success_response(data=data)


def _compute_streak(student_id, institution_id):
    """Count consecutive days (up to today) the student made at least one attempt."""
    from django.utils import timezone
    from datetime import timedelta

    today = timezone.now().date()
    streak = 0
    current_date = today
    while True:
        has_attempt = PracticeEvent.objects.filter(
            student_id=student_id,
            institution_id=institution_id,
            created_at__date=current_date,
        ).exists()
        if not has_attempt:
            break
        streak += 1
        current_date -= timedelta(days=1)
    return streak


class AdminOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        key = _admin_overview_key(institution_id)
        cached = cache.get(key)
        if cached is not None:
            return success_response(data=cached)

        snapshot = InstitutionSnapshot.objects.filter(
            institution_id=institution_id
        ).order_by("-snapshot_date").first()

        if snapshot:
            data = {
                "total_students": snapshot.total_students,
                "total_active": snapshot.total_active,
                "practice_completion_rate": snapshot.practice_completion_rate,
                "resource_utilization_rate": snapshot.resource_utilization_rate,
                "snapshot_date": snapshot.snapshot_date.isoformat(),
            }
        else:
            data = {
                "total_students": 0,
                "total_active": 0,
                "practice_completion_rate": 0.0,
                "resource_utilization_rate": 0.0,
                "snapshot_date": None,
            }

        cache.set(key, data, _ADMIN_CACHE_TTL)
        return success_response(data=data)


class AdminTopPerformersView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        events = PracticeEvent.objects.filter(institution_id=institution_id)
        top = (
            events.values("student_id")
            .annotate(
                total=Count("id"),
                correct=Count("id", filter=Q(is_correct=True)),
            )
            .filter(total__gte=1)
            .order_by("-correct", "-total")[:10]
        )
        data = [
            {
                "student_id": str(r["student_id"]),
                "total_attempts": r["total"],
                "correct_attempts": r["correct"],
                "accuracy_percent": round(r["correct"] / r["total"] * 100, 2) if r["total"] > 0 else 0.0,
            }
            for r in top
        ]
        return success_response(data=data)


class AdminWeakTopicsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        topics = (
            PracticeEvent.objects.filter(institution_id=institution_id)
            .values("topic")
            .annotate(
                attempts=Count("id"),
                correct=Count("id", filter=Q(is_correct=True)),
            )
            .filter(attempts__gte=1)
        )
        weak = sorted(
            [
                {
                    "topic": t["topic"] or "Unknown",
                    "attempts": t["attempts"],
                    "correct": t["correct"],
                    "accuracy_percent": round(t["correct"] / t["attempts"] * 100, 2),
                }
                for t in topics
            ],
            key=lambda x: x["accuracy_percent"],
        )[:10]
        return success_response(data=weak)


class AdminResourceUsageView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        companies = (
            ResourceViewEvent.objects.filter(institution_id=institution_id)
            .values("company_id")
            .annotate(views=Count("id"))
            .order_by("-views")[:10]
        )
        resources = (
            ResourceViewEvent.objects.filter(institution_id=institution_id)
            .values("resource_id")
            .annotate(views=Count("id"))
            .order_by("-views")[:10]
        )
        data = {
            "top_companies": [
                {"company_id": str(r["company_id"]), "views": r["views"]} for r in companies
            ],
            "top_resources": [
                {"resource_id": str(r["resource_id"]), "views": r["views"]} for r in resources
            ],
        }
        return success_response(data=data)


class SuperAdminOverviewView(APIView):
    permission_classes = [IsSuperAdminUser]

    def get(self, request):
        key = _superadmin_overview_key()
        cached = cache.get(key)
        if cached is not None:
            return success_response(data=cached)

        snapshots = InstitutionSnapshot.objects.order_by("institution_id", "-snapshot_date")
        seen = set()
        latest = []
        for s in snapshots:
            if s.institution_id not in seen:
                seen.add(s.institution_id)
                latest.append(s)

        total_institutions = len(latest)
        total_students = sum(s.total_students for s in latest)
        total_active = sum(s.total_active for s in latest)
        avg_completion = (
            sum(s.practice_completion_rate for s in latest) / total_institutions
            if total_institutions > 0 else 0.0
        )

        data = {
            "total_institutions": total_institutions,
            "total_students": total_students,
            "total_active_students": total_active,
            "average_practice_completion_rate": round(avg_completion, 2),
        }
        cache.set(key, data, _SUPERADMIN_CACHE_TTL)
        return success_response(data=data)


class SuperAdminDepartmentsView(APIView):
    permission_classes = [IsSuperAdminUser]

    def get(self, request):
        dept_stats = (
            DailyEngagementSnapshot.objects.values("institution_id", "department")
            .annotate(
                total_attempts=Sum("practice_attempts"),
                total_views=Sum("resource_views"),
                student_count=Count("student_id", distinct=True),
            )
            .order_by("institution_id", "-total_attempts")
        )
        data = [
            {
                "institution_id": str(r["institution_id"]),
                "department": r["department"] or "Unknown",
                "student_count": r["student_count"],
                "total_practice_attempts": r["total_attempts"] or 0,
                "total_resource_views": r["total_views"] or 0,
            }
            for r in dept_stats
        ]
        return success_response(data=data)


class InternalEventView(APIView):
    authentication_classes = []
    permission_classes = [IsServiceKey]
    # Legitimate high-frequency internal traffic (bypasses nginx entirely —
    # called directly on the Docker network) must not share the anon/user
    # DRF throttle buckets meant for external-facing endpoints.
    throttle_classes = []

    def post(self, request):
        serializer = InternalEventSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid event payload.", errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        event_type = data["event_type"]

        if event_type == "practice_attempt":
            PracticeEvent.objects.create(
                student_id=data["student_id"],
                institution_id=data["institution_id"],
                module_id=data["module_id"],
                question_id=data["question_id"],
                topic=data.get("topic", ""),
                difficulty=data.get("difficulty", ""),
                is_correct=data["is_correct"],
            )
            _invalidate_student_cache(data["institution_id"], data["student_id"])
            _invalidate_admin_cache(data["institution_id"])

        elif event_type == "resource_view":
            ResourceViewEvent.objects.create(
                student_id=data["student_id"],
                institution_id=data["institution_id"],
                company_id=data["company_id"],
                resource_id=data["resource_id"],
            )
            _invalidate_admin_cache(data["institution_id"])

        return success_response(
            data={"event_type": event_type},
            status_code=status.HTTP_201_CREATED,
        )
