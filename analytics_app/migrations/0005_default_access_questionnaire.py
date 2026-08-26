from django.db import migrations


def create_default_questionnaire(apps, schema_editor):
    Questionnaire = apps.get_model("analytics_app", "AnalyticsQuestionnaire")
    Question = apps.get_model("analytics_app", "AnalyticsQuestion")
    questionnaire, created = Questionnaire.objects.get_or_create(
        title="LMS access and inclusion survey",
        defaults={
            "purpose": (
                "Help the university understand broad access patterns and improve learning support. "
                "Results are intended for aggregated reporting and service planning."
            ),
            "retention_days": 365,
            "is_active": False,
        },
    )
    if not created:
        return
    questions = [
        (1, "gender", "How do you describe your gender?", "gender", False, []),
        (2, "province", "Which province do you usually access the LMS from?", "region", False, []),
        (
            3,
            "primary_device",
            "Which device do you mainly use for the LMS?",
            "select",
            False,
            ["Mobile phone", "Tablet", "Laptop", "Desktop computer", "Shared or campus computer", "Prefer not to say"],
        ),
        (
            4,
            "connectivity",
            "What connection do you mainly use?",
            "select",
            False,
            ["Mobile data", "Home Wi-Fi", "Campus network", "Public Wi-Fi", "Other", "Prefer not to say"],
        ),
    ]
    for order, key, label, question_type, required, options in questions:
        Question.objects.create(
            questionnaire=questionnaire,
            order=order,
            key=key,
            label=label,
            question_type=question_type,
            is_required=required,
            options=options,
        )


class Migration(migrations.Migration):
    dependencies = [("analytics_app", "0004_analyticsquestionnaire_analyticsquestion_and_more")]

    operations = [migrations.RunPython(create_default_questionnaire, migrations.RunPython.noop)]
