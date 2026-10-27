from django.db import migrations

def assign_department(apps, schema_editor):
    Department = apps.get_model('institutions', 'Department')
    Course = apps.get_model('learning', 'Course')
    department, _ = Department.objects.using(schema_editor.connection.alias).get_or_create(institution_id=1, code='general', defaults={'name': 'General'})
    Course.objects.using(schema_editor.connection.alias).filter(institution_id=1, department__isnull=True).update(department=department)

class Migration(migrations.Migration):
    dependencies = [('learning', '0008_alter_course_options_assessmentattempt_institution_and_more')]
    operations = [migrations.RunPython(assign_department, migrations.RunPython.noop)]
