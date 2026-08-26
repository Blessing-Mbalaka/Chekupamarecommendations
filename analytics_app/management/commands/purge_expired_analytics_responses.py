from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics_app.models import AnalyticsQuestionnaireResponse


class Command(BaseCommand):
    help = "Delete consented questionnaire responses after each questionnaire's configured retention period."

    def handle(self, *args, **options):
        deleted = 0
        for response in AnalyticsQuestionnaireResponse.objects.select_related("questionnaire").iterator():
            expires_at = response.updated_at + timezone.timedelta(days=response.questionnaire.retention_days)
            if expires_at <= timezone.now():
                response.delete()
                deleted += 1
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired analytics questionnaire response(s)."))
