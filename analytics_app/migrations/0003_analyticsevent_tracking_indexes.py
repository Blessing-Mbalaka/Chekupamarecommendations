import django.db.models.deletion
from django.db import migrations, models


def detach_missing_chat_messages(apps, schema_editor):
    AnalyzedQuestion = apps.get_model("analytics_app", "AnalyzedQuestion")
    ChatMessage = apps.get_model("chatbot", "ChatMessage")
    valid_message_ids = ChatMessage.objects.values_list("pk", flat=True)
    AnalyzedQuestion.objects.exclude(message_id__in=valid_message_ids).update(message_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("analytics_app", "0002_questiontheme_analyzedquestion_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="analyticsevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("page_view", "Page View"),
                    ("click", "Click"),
                    ("material_view", "Material View"),
                    ("dwell", "Dwell"),
                    ("chat", "Chat"),
                    ("endpoint", "Endpoint Request"),
                    ("form_submit", "Form Submit"),
                    ("input_interaction", "Input Interaction"),
                    ("download", "Download"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="analyzedquestion",
            name="message",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="question_analysis",
                to="chatbot.chatmessage",
            ),
        ),
        migrations.RunPython(detach_missing_chat_messages, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["event_type", "created_at"], name="analytics_event_type_time"),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["user", "created_at"], name="analytics_user_time"),
        ),
        migrations.AddIndex(
            model_name="analyticsevent",
            index=models.Index(fields=["path", "created_at"], name="analytics_path_time"),
        ),
    ]
