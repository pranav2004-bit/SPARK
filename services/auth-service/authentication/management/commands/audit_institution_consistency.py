import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Audit every account (admin + student) against the super-admin's institution_id. "
        "create_default_superadmin only validates the super-admin's own record — this command "
        "checks everyone else, to catch data drift it cannot see."
    )

    def handle(self, *args, **options):
        super_admin = User.objects.filter(role="super_admin").order_by("created_at").first()
        if super_admin is None:
            raise CommandError("No super-admin account exists — nothing to audit against.")

        canonical_id = super_admin.institution_id
        if not canonical_id:
            raise CommandError(
                "Super-admin has no institution_id set — fix that first "
                "(run create_default_superadmin or check INSTITUTION_ID in .env)."
            )

        suspects = User.objects.exclude(role="super_admin").exclude(institution_id=canonical_id)
        count = suspects.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS(
                f"OK — all accounts match institution_id={canonical_id}."
            ))
            return

        lines = [
            f"Found {count} account(s) inconsistent with institution_id={canonical_id}:",
        ]
        for u in suspects[:50]:  # cap output for very large tables
            identifier = u.email or u.student_id or str(u.id)
            lines.append(f"  - {identifier} (role={u.role}, institution_id={u.institution_id})")
        if count > 50:
            lines.append(f"  ... and {count - 50} more (truncated).")

        report = "\n".join(lines)
        logger.warning("INSTITUTION CONSISTENCY AUDIT: %s", report)
        raise CommandError(report)
