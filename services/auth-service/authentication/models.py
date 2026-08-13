import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    STUDENT = "student", "Student"
    SUPER_ADMIN = "super_admin", "Super Admin"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role=UserRole.STUDENT, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    # student_id is used for student login; null for admin/super_admin
    student_id = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True)
    role = models.CharField(max_length=15, choices=UserRole.choices, default=UserRole.STUDENT)
    # institution_id ties every account (super_admin, admin, student) to their college
    institution_id = models.UUIDField(db_index=True)
    # Display name — used for admin accounts; empty for students/super_admin
    name = models.CharField(max_length=150, blank=True, default="")
    # Department — used for admin accounts
    department = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # For students only — tracks profile completion state
    is_profile_completed = models.BooleanField(default=False)
    # Set True on account creation — forces password change before use
    force_password_change = models.BooleanField(default=False)
    # Incremented to invalidate all existing tokens for this user
    token_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"], name="idx_users_email"),
            models.Index(fields=["role"], name="idx_users_role"),
            models.Index(fields=["institution_id"], name="idx_users_institution_id"),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"
