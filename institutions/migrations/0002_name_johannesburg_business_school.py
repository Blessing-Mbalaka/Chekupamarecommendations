from django.db import migrations


def name_johannesburg_business_school(apps, schema_editor):
    Institution = apps.get_model("institutions", "Institution")
    database = schema_editor.connection.alias
    institutions = Institution.objects.using(database)
    if institutions.filter(slug="jbs").exclude(pk=1).exists():
        raise RuntimeError("Institution code 'jbs' is already in use.")
    institutions.filter(pk=1, is_original=True).update(
        name="Johannesburg Business School",
        slug="jbs",
    )


def restore_original_name(apps, schema_editor):
    Institution = apps.get_model("institutions", "Institution")
    Institution.objects.using(schema_editor.connection.alias).filter(
        pk=1,
        is_original=True,
    ).update(name="Original Institution", slug="original")


class Migration(migrations.Migration):
    dependencies = [("institutions", "0001_initial")]

    operations = [
        migrations.RunPython(name_johannesburg_business_school, restore_original_name),
    ]
