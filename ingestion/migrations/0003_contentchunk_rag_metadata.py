import hashlib
import re

from django.db import migrations, models


def backfill_chunk_metadata(apps, schema_editor):
    ContentChunk = apps.get_model("ingestion", "ContentChunk")
    for chunk in ContentChunk.objects.all().iterator():
        text = chunk.text or ""
        chunk.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunk.token_count = len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))
        chunk.chunking_strategy = "legacy-fixed-window"
        chunk.embedding_model = chunk.embedding_backend
        chunk.save(
            update_fields=[
                "content_hash",
                "token_count",
                "chunking_strategy",
                "embedding_model",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0002_researchrun_researchtheme_researchvideo_and_more")]

    operations = [
        migrations.AddField(
            model_name="contentchunk",
            name="content_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="contentchunk",
            name="token_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="contentchunk",
            name="page_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contentchunk",
            name="section_title",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="contentchunk",
            name="chunking_strategy",
            field=models.CharField(default="legacy-fixed-window", max_length=80),
        ),
        migrations.AddField(
            model_name="contentchunk",
            name="embedding_model",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="contentchunk",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(backfill_chunk_metadata, migrations.RunPython.noop),
    ]
