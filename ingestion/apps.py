from django.apps import AppConfig


class IngestionConfig(AppConfig):
    name = 'ingestion'

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from ingestion.models import ContentChunk
        from ingestion.services.vector_store import _invalidate_cache_for_chunk

        post_save.connect(_invalidate_cache_for_chunk, sender=ContentChunk)
        post_delete.connect(_invalidate_cache_for_chunk, sender=ContentChunk)
