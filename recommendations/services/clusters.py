from learning.models import Material
from recommendations.models import MaterialEmbeddingCluster

from .engine import _material_text
from .llm import embed_text


def _cluster_label(material: Material) -> str:
    if material.topic:
        return material.topic.title
    if material.tags:
        return material.tags.split(",")[0].strip()
    return material.course.title


def update_material_clusters(materials=None):
    materials = materials or Material.objects.select_related("course", "topic").filter(is_validated=True)
    clusters = []
    for material in materials:
        embedding, backend = embed_text(material.semantic_text or _material_text(material))
        if not embedding:
            continue
        keywords = ", ".join(
            part for part in [material.topic.title if material.topic else "", material.tags, material.source_type] if part
        )[:255]
        cluster, _ = MaterialEmbeddingCluster.objects.update_or_create(
            material=material,
            defaults={
                "cluster_label": _cluster_label(material),
                "embedding_backend": backend,
                "x": float(embedding[0]) if len(embedding) > 0 else 0.0,
                "y": float(embedding[1]) if len(embedding) > 1 else 0.0,
                "z": float(embedding[2]) if len(embedding) > 2 else 0.0,
                "keywords": keywords,
            },
        )
        clusters.append(cluster)
    return clusters
