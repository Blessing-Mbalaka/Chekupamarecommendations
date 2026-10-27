from django.apps import AppConfig
from django.db.models.signals import m2m_changed, post_migrate

class InstitutionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'institutions'
    def ready(self):
        from .tenancy import validate_institution_m2m
        m2m_changed.connect(validate_institution_m2m, dispatch_uid='institution_links')
        post_migrate.connect(ensure_original, sender=self)

def ensure_original(sender, **kwargs):
    from .models import Institution
    Institution.objects.get_or_create(pk=1, defaults={'name': 'Johannesburg Business School', 'slug': 'jbs', 'is_original': True})
