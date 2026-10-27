from django.contrib.auth.models import UserManager
from institutions.tenancy import InstitutionQuerySet

class InstitutionUserManager(UserManager.from_queryset(InstitutionQuerySet)):
    def get_queryset(self):
        return super().get_queryset()._apply_institution()
