from institutions.models import InstitutionOwnedModel
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    LECTURER = "lecturer", "Lecturer"
    TA = "ta", "Teaching Assistant"
    STUDENT = "student", "Student"


class User(AbstractUser, InstitutionOwnedModel):
    from .managers import InstitutionUserManager
    objects = InstitutionUserManager()
    department = models.ForeignKey("institutions.Department", on_delete=models.PROTECT, null=True, blank=True)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STUDENT)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=30, blank=True)
    student_number = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def get_absolute_url(self):
        return reverse("accounts:profile")

    @property
    def effective_role_display(self) -> str:
        """Show platform privileges before the institution-level role field."""
        if self.is_superuser:
            return "Platform Administrator"
        if self.is_staff and self.role == UserRole.STUDENT:
            return "Staff"
        return self.get_role_display()


class StudentProfile(InstitutionOwnedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    identifiers = models.TextField(
        blank=True,
        help_text="Free-form identifiers, background, or notes shared by the student.",
    )
    challenges = models.TextField(
        blank=True,
        help_text="Large free-text field capturing personal learning challenges.",
    )
    goals = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile for {self.user}"

# Create your models here.
