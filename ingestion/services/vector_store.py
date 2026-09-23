from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from django.core.cache import cache
from django.db import transaction

from ingestion.models import ContentChunk
from learning.models import Material
from recommendations.services.llm import embed_text, embed_texts, embedding_model_name


CHUNKING_STRATEGY = "semantic-cohesion-v1"
RETRIEVAL_CACHE_TTL_SECONDS = 300
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
WORD_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    page_number: int | None = None
    section_title: str = ""


@dataclass(frozen=True)
class _TextUnit:
    text: str
    page_number: int | None
    section_title: str


def clean_text(value: str) -> str:
    """Compact metadata/transcript text and remove short bracketed video labels."""

    value = re.sub(r"\[[^\]]{0,30}\]", " ", value or " ")
    value = re.sub(r"\s+", " ", value or " ")
    return value.strip()


def normalize_document_text(value: str) -> str:
    """Normalize extraction noise without throwing away paragraph/page boundaries."""

    page_marker = "__RAG_PAGE_BREAK__"
    value = (
        (value or "")
        .replace("\x00", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\f", f"\n{page_marker}\n")
    )
    value = re.sub(r"(?<=\w)-\n(?=\w)", "", value)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.replace(page_marker, "\f").strip()


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    if not words or len(words) > 14 or len(text) > 140 or text[-1:] in ".,;?!":
        return False
    letters = [char for char in text if char.isalpha()]
    uppercase_ratio = sum(char.isupper() for char in letters) / max(1, len(letters))
    return text.endswith(":") or uppercase_ratio > 0.7 or text.istitle()


def _split_long_unit(text: str, max_words: int = 90) -> list[str]:
    sentences = [part.strip() for part in SENTENCE_BOUNDARY.split(text) if part.strip()]
    pieces: list[str] = []
    for sentence in sentences or [text]:
        words = sentence.split()
        pieces.extend(" ".join(words[start : start + max_words]) for start in range(0, len(words), max_words))
    return [piece for piece in pieces if piece]


def _document_units(value: str) -> list[_TextUnit]:
    units: list[_TextUnit] = []
    section_title = ""
    pages = normalize_document_text(value).split("\f")
    for page_index, page in enumerate(pages, start=1):
        page_number = page_index if len(pages) > 1 else None
        blocks = [block.strip() for block in re.split(r"\n\s*\n", page) if block.strip()]
        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(lines) == 1 and _looks_like_heading(lines[0]):
                section_title = lines[0].rstrip(":")[:500]
                continue
            paragraph = " ".join(lines)
            for piece in _split_long_unit(paragraph):
                units.append(_TextUnit(piece, page_number, section_title))
    return units


def _adjacent_semantic_similarities(units: list[_TextUnit]) -> list[float]:
    """Cheap local semantic boundary signal; embeddings are reserved for final chunks."""

    if len(units) < 2:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1).fit_transform(
            unit.text for unit in units
        )
        return [float(matrix[index - 1].multiply(matrix[index]).sum()) for index in range(1, len(units))]
    except (ImportError, ValueError):
        return [0.0] * (len(units) - 1)


def split_document(
    value: str,
    *,
    target_words: int = 260,
    max_words: int = 420,
    min_words: int = 120,
    overlap_words: int = 45,
) -> list[ChunkDraft]:
    """Create sentence-safe chunks, breaking near low-cohesion or structural boundaries."""

    units = _document_units(value)
    if not units:
        return []
    similarities = _adjacent_semantic_similarities(units)
    nonzero = sorted(score for score in similarities if score > 0)
    low_cohesion = nonzero[max(0, len(nonzero) // 4 - 1)] if nonzero else 0.0
    chunks: list[ChunkDraft] = []
    current: list[_TextUnit] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        if not current:
            return
        chunks.append(
            ChunkDraft(
                text=" ".join(unit.text for unit in current).strip(),
                page_number=current[0].page_number,
                section_title=current[0].section_title,
            )
        )
        overlap: list[_TextUnit] = []
        overlap_size = 0
        for unit in reversed(current):
            overlap.insert(0, unit)
            overlap_size += len(unit.text.split())
            if overlap_size >= overlap_words:
                break
        current = overlap
        current_words = overlap_size

    for index, unit in enumerate(units):
        unit_words = len(unit.text.split())
        structure_changed = bool(
            current
            and (
                unit.page_number != current[-1].page_number
                or (unit.section_title and unit.section_title != current[-1].section_title)
            )
        )
        semantic_break = index > 0 and similarities[index - 1] <= low_cohesion
        would_overflow = current_words + unit_words > max_words
        ready_for_boundary = current_words >= min_words and (
            would_overflow or structure_changed or (current_words >= target_words and semantic_break)
        )
        if ready_for_boundary:
            flush()
        current.append(unit)
        current_words += unit_words
    flush()

    if len(chunks) > 1 and len(chunks[-1].text.split()) < min_words // 2:
        tail = chunks.pop()
        previous = chunks.pop()
        chunks.append(
            ChunkDraft(
                text=f"{previous.text} {tail.text}".strip(),
                page_number=previous.page_number,
                section_title=previous.section_title or tail.section_title,
            )
        )
    return chunks


def split_text(value: str, *, words_per_chunk: int = 260, overlap: int = 45) -> list[str]:
    """Compatibility wrapper returning just chunk text."""

    return [
        draft.text
        for draft in split_document(
            value,
            target_words=words_per_chunk,
            max_words=max(words_per_chunk + 160, words_per_chunk),
            min_words=max(40, words_per_chunk // 2),
            overlap_words=overlap,
        )
    ]


def material_source_text(material: Material) -> str:
    if material.file:
        filename = material.file.name.lower()
        try:
            material.file.open("rb")
            if filename.endswith((".txt", ".md", ".csv", ".vtt", ".srt")):
                return material.file.read().decode("utf-8", errors="replace")
            if filename.endswith(".pdf"):
                from pypdf import PdfReader

                return "\n\f\n".join(page.extract_text() or "" for page in PdfReader(material.file).pages)
            if filename.endswith(".docx"):
                from docx import Document

                return "\n\n".join(paragraph.text for paragraph in Document(material.file).paragraphs)
        except (OSError, ValueError, ImportError):
            pass
        finally:
            material.file.close()
        return material.semantic_text
    if material.semantic_text:
        return material.semantic_text
    return ""


def index_material(material: Material, *, text: str = "", research_video=None) -> list[ContentChunk]:
    source_text = normalize_document_text(text or material_source_text(material))
    drafts = split_document(source_text)
    embedding_results = (
        [embed_text(drafts[0].text)]
        if len(drafts) == 1
        else embed_texts([draft.text for draft in drafts])
    )
    pending: list[ContentChunk] = []
    for ordinal, (draft, embedding_result) in enumerate(zip(drafts, embedding_results)):
        embedding, backend = embedding_result
        pending.append(
            ContentChunk(
                material=material,
                research_video=research_video,
                ordinal=ordinal,
                text=draft.text,
                content_hash=hashlib.sha256(draft.text.encode("utf-8")).hexdigest(),
                token_count=len(WORD_PATTERN.findall(draft.text)),
                page_number=draft.page_number,
                section_title=draft.section_title,
                chunking_strategy=CHUNKING_STRATEGY,
                embedding=embedding,
                embedding_backend=backend,
                embedding_model=embedding_model_name(backend),
                metadata={"source_type": material.source_type, "course_id": material.course_id},
            )
        )
    with transaction.atomic():
        ContentChunk.objects.filter(material=material).delete()
        indexed = ContentChunk.objects.bulk_create(pending)
        if source_text and material.semantic_text != source_text:
            material.semantic_text = source_text
            material.save(update_fields=["semantic_text"])
    invalidate_retrieval_cache(material.course_id)
    return indexed


def _corpus_cache_key(course_id) -> str:
    return f"rag-corpus:{course_id or 'all'}"


def invalidate_retrieval_cache(course_id=None) -> None:
    """Drop the cached scoring corpus for a course, and the cross-course cache that also covers it."""

    cache.delete_many({_corpus_cache_key(course_id), _corpus_cache_key(None)})


def _invalidate_cache_for_chunk(sender, instance, **kwargs) -> None:
    """Signal receiver so any ContentChunk create/delete (not just index_material) busts the corpus cache."""

    course_id = None
    try:
        course_id = instance.material.course_id
    except Material.DoesNotExist:
        pass
    invalidate_retrieval_cache(course_id)



def _load_scoring_corpus(course) -> dict:
    """Cheap, cached id/text/embedding tuples used for scoring; full rows are only fetched for winners."""

    course_id = course.pk if course else None
    cache_key = _corpus_cache_key(course_id)
    corpus = cache.get(cache_key)
    if corpus is not None:
        return corpus

    queryset = ContentChunk.objects.filter(material__is_validated=True)
    if course:
        queryset = queryset.filter(material__course=course)
    rows = list(queryset.values("id", "text", "embedding"))
    corpus = {
        "ids": [row["id"] for row in rows],
        "texts": [row["text"] for row in rows],
        "embeddings": [row["embedding"] for row in rows],
    }
    cache.set(cache_key, corpus, timeout=RETRIEVAL_CACHE_TTL_SECONDS)
    return corpus


def _tokens(value: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall((value or "").lower()) if len(token) > 2]


def _bm25_scores(texts: list[str], query_tokens: list[str]) -> list[float]:
    if not texts or not query_tokens:
        return [0.0] * len(texts)
    documents = [Counter(_tokens(text)) for text in texts]
    lengths = [sum(document.values()) for document in documents]
    average_length = sum(lengths) / max(1, len(lengths))
    document_frequency = Counter(
        token for token in set(query_tokens) for document in documents if token in document
    )
    k1, b = 1.5, 0.75
    scores: list[float] = []
    for document, length in zip(documents, lengths):
        score = 0.0
        for token in query_tokens:
            frequency = document[token]
            if not frequency:
                continue
            frequency_docs = document_frequency[token]
            inverse_frequency = math.log(1 + (len(documents) - frequency_docs + 0.5) / (frequency_docs + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / max(1.0, average_length))
            score += inverse_frequency * (frequency * (k1 + 1) / denominator)
        scores.append(score)
    return scores


def _semantic_scores(query_embedding: list[float], embeddings: list[list[float]]) -> list[float]:
    """Vectorized cosine similarity against every chunk embedding in one matmul instead of per-chunk loops."""

    if not query_embedding:
        return [0.0] * len(embeddings)
    import numpy as np

    query_vector = np.asarray(query_embedding, dtype=np.float64)
    query_norm = np.linalg.norm(query_vector)
    valid_indices = [
        index
        for index, embedding in enumerate(embeddings)
        if embedding and len(embedding) == len(query_embedding)
    ]
    if not query_norm or not valid_indices:
        return [0.0] * len(embeddings)

    matrix = np.asarray([embeddings[index] for index in valid_indices], dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1.0
    similarities = (matrix @ query_vector) / (norms * query_norm)

    scores = [0.0] * len(embeddings)
    for position, chunk_index in enumerate(valid_indices):
        scores[chunk_index] = float(similarities[position])
    return scores


def retrieve_chunks(query: str, *, course=None, limit: int = 5) -> list[dict]:
    corpus = _load_scoring_corpus(course)
    if not corpus["ids"]:
        return []

    query_embedding, _ = embed_text(query)
    semantic_scores = _semantic_scores(query_embedding, corpus["embeddings"])
    lexical_scores = _bm25_scores(corpus["texts"], _tokens(query))
    max_semantic = max(semantic_scores, default=0.0)
    max_lexical = max(lexical_scores, default=0.0)
    has_semantic = max_semantic > 0
    has_lexical = max_lexical > 0

    candidates = []
    for chunk_id, semantic, lexical in zip(corpus["ids"], semantic_scores, lexical_scores):
        semantic_normalized = semantic / max_semantic if has_semantic else 0.0
        lexical_normalized = lexical / max_lexical if has_lexical else 0.0
        if has_semantic and has_lexical:
            score = 0.65 * semantic_normalized + 0.35 * lexical_normalized
        elif has_semantic:
            score = semantic_normalized
        else:
            score = lexical_normalized
        if lexical > 0 or semantic > 0.15:
            candidates.append((score, semantic, lexical, chunk_id))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    winners = candidates[:limit]
    if not winners:
        return []

    # Only hydrate full chunk/material rows for the handful of chunks that actually made the cut.
    chunks_by_id = {
        chunk.pk: chunk
        for chunk in ContentChunk.objects.select_related("material", "material__course", "material__topic").filter(
            pk__in=[chunk_id for *_, chunk_id in winners], material__is_validated=True
        )
    }
    return [
        {
            "chunk": chunk,
            "material": chunk.material,
            "score": round(score, 4),
            "semantic_score": round(semantic, 4),
            "bm25_score": round(lexical, 4),
            "text": chunk.text,
        }
        for score, semantic, lexical, chunk_id in winners
        if (chunk := chunks_by_id.get(chunk_id)) is not None
    ]
