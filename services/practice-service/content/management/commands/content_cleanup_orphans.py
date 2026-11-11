from django.core.management.base import BaseCommand
from django.utils import timezone

from content.media import _delete_object
from content.models import ContentMediaOrphan, ContentQuestionVersion


class Command(BaseCommand):
    help = (
        "Delete S3 objects recorded in the content orphan ledger that no question version references. "
        "Dry run by default; pass --apply to delete."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually delete (default is dry run).")

    def handle(self, *args, **options):
        apply = options["apply"]
        pending = ContentMediaOrphan.objects.filter(cleaned_at__isnull=True)
        deleted = skipped = failed = 0
        for orphan in pending:
            if ContentQuestionVersion.objects.filter(image_key=orphan.key).exists():
                skipped += 1
                self.stdout.write(f"skip (still referenced): {orphan.key}")
                continue
            if not apply:
                self.stdout.write(f"would delete: {orphan.key}")
                continue
            try:
                _delete_object(orphan.key)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"failed: {orphan.key}: {exc}")
                continue
            orphan.cleaned_at = timezone.now()
            orphan.save(update_fields=["cleaned_at"])
            deleted += 1
        mode = "applied" if apply else "dry run"
        self.stdout.write(f"{mode}: deleted={deleted} skipped={skipped} failed={failed}")
