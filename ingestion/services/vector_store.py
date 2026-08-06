from __future__ import annotations

import re

from ingestion.models import ContentChunk
from learning.models import Material
from recommendations.services.llm import cosine_similarity, embed_text


def clean_text(value: str) -> str:
    value = re.sub(r"\[[^\]]{0,30}\]", " ", value or " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def split_text(value: str, *, words_per_chunk: int = 220, overlap: int = 35) -> list[str]:
    words = clean_text(value).split()
    if not words:
        return []
    step = max(1, words_per_chunk - overlap)
    return [" ".join(words[start : start + words_per_chunk]) for start in range(0, len(words), step)]


def material_source_text(material: Material) -> str:
    if material.semantic_text:
        return material.semantic_text
    if material.file:
        filename = material.file.name.lower()
        try:
            material.file.open("rb")
            if filename.endswith((".txt", ".md", ".csv", ".vtt", ".srt")):
                return material.file.read().decode("utf-8", errors="replace")
            if filename.endswith(".pdf"):
                from pypdf import PdfReader

                return "\n".join(page.extract_text() or "" for page in PdfReader(material.file).pages)
            if filename.endswith(".docx"):
                from docx import Document

                return "\n".join(paragraph.text for paragraph in Document(material.file).paragraphs)
        except (OSError, ValueError, ImportError):
            pass
        finally:
            material.file.close()
        return ""
    return " ".join(
        filter(
            None,
            [
                material.title,
                material.description,
                material.authors,
                material.publisher,
                material.journal_name,
                material.doi,
                material.isbn,
                material.tags,
            ],
        )
    )


def index_material(material: Material, *, text: str = "", research_video=None) -> list[ContentChunk]:
    source_text = clean_text(text or material_source_text(material))
    ContentChunk.objects.filter(material=material).delete()
    indexed = []
    for ordinal, chunk_text in enumerate(split_text(source_text)):
        embedding, backend = embed_text(chunk_text)
        indexed.append(
            ContentChunk.objects.create(
                material=material,
                research_video=research_video,
                ordinal=ordinal,
                text=chunk_text,
                embedding=embedding,
                embedding_backend=backend,
            )
        )
    if source_text and material.semantic_text != source_text:
        material.semantic_text = source_text
        material.save(update_fields=["semantic_text"])
    return indexed


def retrieve_chunks(query: str, *, course=None, limit: int = 5) -> list[dict]:
    queryset = ContentChunk.objects.select_related("material", "material__course", "material__topic")
    queryset = queryset.filter(material__is_validated=True)
    if course:
        queryset = queryset.filter(material__course=course)
    chunks = list(queryset[:1000])
    if not chunks:
        return []
    query_embedding, _ = embed_text(query)
    query_tokens = {word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 2}
    ranked = []
    for chunk in chunks:
        semantic = cosine_similarity(query_embedding, chunk.embedding) if query_embedding and chunk.embedding else 0.0
        chunk_tokens = set(re.findall(r"[a-z0-9]+", chunk.text.lower()))
        lexical = len(query_tokens & chunk_tokens) / max(1, len(query_tokens))
        score = semantic if semantic else lexical
        if score > 0:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "chunk": chunk,
            "material": chunk.material,
            "score": round(score, 4),
            "text": chunk.text,
        }
        for score, chunk in ranked[:limit]
    ]
