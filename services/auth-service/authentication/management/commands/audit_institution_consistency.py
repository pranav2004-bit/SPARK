import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Audit every account (super_admin + admin + student) against the IT account's "
        "institution_id. create_default_it only validates the IT account's own record "
        "(2026-08-20: IT is now the bootstrapped root, replacing super_admin) — this "
        "command checks everyone else, to catch data drift it cannot see."
    )

    def handle(self, *args, **options):
        it_user = User.objects.filter(role="it").order_by("created_at").first()
        if it_user is None:
            raise CommandError("No IT account exists — nothing to audit against.")

        canonical_id = it_user.institution_id
        if not canonical_id:
            raise CommandError(
                "IT account has no institution_id set — fix that first "
                "(run create_default_it or check INSTITUTION_ID in .env)."
            )

        suspects = User.objects.exclude(role="it").exclude(institution_id=canonical_id)
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
