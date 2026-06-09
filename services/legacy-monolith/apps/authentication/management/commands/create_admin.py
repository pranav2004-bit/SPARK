from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

ADMIN_EMAIL = "aptlogic@gmail.com"
ADMIN_PASSWORD = "000346"


class Command(BaseCommand):
    help = "Create the default AptLogic admin user if it does not already exist"

    def handle(self, *args, **options):
        if User.objects.filter(email=ADMIN_EMAIL).exists():
            self.stdout.write(self.style.WARNING(
                f"Admin user '{ADMIN_EMAIL}' already exists — skipping."
            ))
            return

        User.objects.create_user(
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
            role="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Admin user '{ADMIN_EMAIL}' created successfully."
        ))
