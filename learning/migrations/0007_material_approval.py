from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def reset_external_material_approval(apps, schema_editor):
    Material = apps.get_model("learning", "Material")
    Material.objects.filter(source_origin="external").update(
        is_validated=False,
        approved_by=None,
        approved_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("learning", "0006_quizquestion_is_reviewed"),
    ]

    operations = [
        migrations.AddField(
            model_name="material",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="material",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_materials",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(reset_external_material_approval, migrations.RunPython.noop),
    ]
