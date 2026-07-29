from django.contrib import admin

from .models import MaterialEmbeddingCluster, Recommendation


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("student", "material", "score", "source", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("student__username", "material__title", "reason")


@admin.register(MaterialEmbeddingCluster)
class MaterialEmbeddingClusterAdmin(admin.ModelAdmin):
    list_display = ("material", "cluster_label", "embedding_backend", "x", "y", "z", "updated_at")
    list_filter = ("cluster_label", "embedding_backend")
    search_fields = ("material__title", "keywords")

# Register your models here.
