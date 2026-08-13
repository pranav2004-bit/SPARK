from celery import shared_task
from django.utils import timezone
from datetime import timedelta


@shared_task
def run_nightly_aggregation():
    """Aggregate raw events into daily snapshots. Runs nightly at 01:00 UTC."""
    from django.db.models import Count, Q

    from .models import (
        PracticeEvent, ResourceViewEvent,
        DailyEngagementSnapshot, InstitutionSnapshot,
    )

    yesterday = (timezone.now() - timedelta(days=1)).date()

    # ── DailyEngagementSnapshot ────────────────────────────────────────
    practice_by_student = (
        PracticeEvent.objects.filter(created_at__date=yesterday)
        .values("student_id", "institution_id")
        .annotate(
            attempts=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
    )
    resource_by_student = (
        ResourceViewEvent.objects.filter(created_at__date=yesterday)
        .values("student_id", "institution_id")
        .annotate(views=Count("id"))
    )

    resource_lookup = {
        (str(r["student_id"]), str(r["institution_id"])): r["views"]
        for r in resource_by_student
    }

    snapshots_created = 0
    for row in practice_by_student:
        sid, iid = str(row["student_id"]), str(row["institution_id"])
        views = resource_lookup.get((sid, iid), 0)
        DailyEngagementSnapshot.objects.update_or_create(
            student_id=row["student_id"],
            snapshot_date=yesterday,
            defaults={
                "institution_id": row["institution_id"],
                "practice_attempts": row["attempts"],
                "correct_attempts": row["correct"],
                "resource_views": views,
            },
        )
        snapshots_created += 1

    # ── InstitutionSnapshot ────────────────────────────────────────────
    practice_events = PracticeEvent.objects.filter(created_at__date=yesterday)
    institutions = practice_events.values("institution_id").distinct()

    institution_snapshots = 0
    for row in institutions:
        iid = row["institution_id"]
        total_students = (
            PracticeEvent.objects.filter(institution_id=iid)
            .values("student_id")
            .distinct()
            .count()
        )
        active_today = (
            PracticeEvent.objects.filter(institution_id=iid, created_at__date=yesterday)
            .values("student_id")
            .distinct()
            .count()
        )
        total_attempts = practice_events.filter(institution_id=iid).count()
        correct_attempts = practice_events.filter(institution_id=iid, is_correct=True).count()
        completion_rate = (correct_attempts / total_attempts * 100) if total_attempts > 0 else 0.0

        total_resource_views = ResourceViewEvent.objects.filter(
            institution_id=iid, created_at__date=yesterday
        ).count()
        resource_rate = (total_resource_views / max(active_today, 1)) if active_today > 0 else 0.0

        InstitutionSnapshot.objects.update_or_create(
            institution_id=iid,
            snapshot_date=yesterday,
            defaults={
                "total_students": total_students,
                "total_active": active_today,
                "practice_completion_rate": round(completion_rate, 2),
                "resource_utilization_rate": round(resource_rate, 2),
            },
        )
        institution_snapshots += 1

    return {
        "date": yesterday.isoformat(),
        "engagement_snapshots": snapshots_created,
        "institution_snapshots": institution_snapshots,
    }
