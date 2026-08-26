from django.db import migrations
from django.utils import timezone


def publish_default_questionnaire(apps, schema_editor):
    Questionnaire = apps.get_model("analytics_app", "AnalyticsQuestionnaire")
    Questionnaire.objects.filter(title="LMS access and inclusion survey").update(
        is_active=True,
        reviewed_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [("analytics_app", "0005_default_access_questionnaire")]

    operations = [migrations.RunPython(publish_default_questionnaire, migrations.RunPython.noop)]
