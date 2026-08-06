# Recommendation Engine Master Plan

## Product outcome

Build a source-grounded learning platform that turns structured lecturer uploads, academic API discovery, and YouTube research collections into a searchable knowledge base, topic map, and recommendation system. Every chatbot answer must be traceable to persisted, indexed full text.

## Non-negotiable behavior

1. The chatbot answers only from `ContentChunk` records stored in the database.
2. YouTube metadata alone is never treated as RAG evidence.
3. A user must paste or upload a YouTube transcript before that video can influence an answer.
4. Every grounded answer exposes the indexed materials it used.
5. Discovery, validation, indexing, topic modelling, recommendation, and chat remain separate stages.
6. Live academic API metadata may be suggested and embedded, but cannot ground an answer until full text is uploaded and indexed.
7. Quiz generation receives only indexed excerpts; generated JSON remains an editable lecturer draft.

## Target data flow

```text
YouTube seed URL
  -> resolve the real video title
  -> clean title into a research query
  -> YouTube Data API search
  -> collect top N video metadata
  -> store research run and videos
  -> user uploads/pastes transcripts
  -> remove VTT/SRT timestamps and markup
  -> split into overlapping chunks
  -> create embeddings and persist chunks
  -> LDA (or optional BERTopic) theme extraction
  -> persist multi-theme memberships
  -> render overlapping topic circles
  -> retrieve relevant stored chunks
  -> grounded chatbot answer and recommendations
```

## Implemented architecture

### Research ingestion

- `ResearchRun` records the seed URL, resolved title, derived query, requested result count, model, status, course, and optional course topic.
- `ResearchVideo` persists YouTube metadata and manual transcript state.
- `ResearchTheme` persists a topic label, keywords, and visualization coordinates/radius.
- `ResearchVideoTheme` is a weighted many-to-many relationship, allowing genuine overlap rather than forcing each video into one cluster.
- The YouTube Data API is used for title/search/metadata. Set `YOUTUBE_API_KEY` in `.env`.
- Transcript fetching is deliberately not automated.

### Vector storage and RAG

- `ContentChunk` is the retrieval boundary and persisted vector store for this Django/SQLite deployment.
- Uploaded PDF, DOCX, TXT, Markdown, CSV, VTT, and SRT files are extracted and indexed.
- Manually supplied YouTube transcripts are cleaned and indexed.
- Semantic retrieval is used when Gemini/Ollama embeddings are available; lexical retrieval remains a deterministic fallback.
- Chat refreshes configured OpenAlex, Crossref, Semantic Scholar, Springer Nature, and Google Scholar results through a 15-minute query cache; Google Scholar uses the maintained SerpApi Python SDK with `engine=google_scholar`.
- API results are stored with provider, endpoint, DOI/ISBN, author, journal, publisher, and preview provenance, but remain clearly labelled external suggestions until their full text is indexed.
- Chat returns a refusal when no indexed chunk matches, even when useful external suggestions are available.

### Structured curation

- Superusers can classify resources as uploaded files, websites, videos, academic papers, journal articles, books, blogs, or other material.
- The curation portal and Django admin capture authors, publisher, journal, volume/issue, DOI, ISBN, year, links, and preview URLs.
- Saving a validated uploaded file through Django admin refreshes its RAG chunks.
- Local PDF embeds use an authenticated `SAMEORIGIN` preview endpoint; external embeds retain provider-controlled iframe restrictions.

### Quiz lifecycle

- Teaching staff create course quizzes in a dedicated builder, add manual questions, or select indexed materials for LLM-generated JSON drafts.
- Generated questions retain source-material and backend provenance and remain editable before publication.
- Published quizzes are available only to enrolled students; attempts, responses, points, correctness, and feedback are persisted.
- Exact repeated RAG questions reuse a five-minute cache keyed by the question and current retrieved chunk IDs; conversation messages remain permanently stored.

### Topic modelling and visualization

- LDA uses scikit-learn when installed.
- BERTopic is an optional selection and runs only when its package/model dependencies are installed; otherwise modelling falls back to LDA.
- If the modelling dependency is unavailable, a deterministic keyword fallback keeps the workflow operational and labels the run accordingly.
- A video can belong to several themes based on model weights.
- The curation console renders theme regions as overlapping SVG circles and lists each video's theme memberships.

## Functional audit

| Area | Previous state | Current state |
|---|---|---|
| YouTube URL parsing | Stored manual links only | Watch, short, live, embed, and `youtu.be` IDs parsed |
| Title-derived research | Missing | Resolved title is cleaned into the search query |
| YouTube search/metadata | Missing | Top N search plus detail metadata persisted |
| Transcripts | Missing | Manual paste/TXT/VTT/SRT upload with cleaning |
| Topic modelling | Single label from course/topic/tag | Persisted weighted LDA/BERTopic themes |
| Overlap visualization | Three embedding coordinates only | Multi-membership overlapping circle map |
| Vector database | Material-level JSON only | Chunk-level persisted embeddings and provenance |
| Chat grounding | Could call external discovery and use broad fallback | Retrieval-only; refuses without indexed evidence |
| Citations | Recommendation cards only | Answer metadata lists exact indexed sources |
| Academic discovery | Admin-only search | Configured APIs refresh cached, labelled chat suggestions |
| Structured library | Generic file/paper records | Videos, journals, books, blogs, DOI/ISBN and publication metadata |
| Document extraction | Text-like files only | PDF, DOCX and text-family extraction with safe no-text fallback |

## Delivery roadmap

### Phase 1 — completed foundation

- Accounts, roles, courses, topics, assessments, materials, analytics, curation, and recommendations.
- Gemini and Ollama abstraction with deterministic fallbacks.

### Phase 2 — completed research/RAG core

- YouTube title-derived research runs.
- Top N video metadata persistence.
- Manual transcript workflow.
- Chunk persistence and retrieval-only chat.
- LDA/optional BERTopic themes and overlap visualization.
- Automated unit and integration coverage.

### Phase 3 — production hardening

- Move long YouTube searches, modelling, and embedding work to Celery/RQ background jobs.
- Replace SQLite JSON vectors with PostgreSQL + pgvector when data volume exceeds a small teaching deployment.
- Add PPTX/EPUB extraction and page/slide-level citation provenance.
- Add transcript versioning, moderation, validation, and lecturer approval.
- Add retry/rate-limit handling and quota reporting for YouTube.
- Add per-course access checks to every retrieved chunk.

### Phase 4 — evaluation and governance

- RAG faithfulness and retrieval-recall test sets.
- Source coverage, stale content, empty transcript, and embedding health dashboards.
- Student feedback on answers and recommendation usefulness.
- Data retention, copyright, accessibility, and consent policy review.

## Configuration

```text
YOUTUBE_API_KEY=...
OPENALEX_API_KEY=...               # optional/provider-dependent
CROSSREF_MAILTO=...                # recommended identification
SEMANTIC_SCHOLAR_API_KEY=...       # optional public-mode enhancement
SPRINGER_API_KEY=...               # optional
SERPAPI_API_KEY=...                # optional Google Scholar provider
GEMINI_API_KEY=...                 # optional
GEMINI_EMBED_MODEL=...             # optional
OLLAMA_BASE_URL=...                # optional local fallback
OLLAMA_EMBED_MODEL=...             # optional local fallback
```

## Acceptance criteria

- A superuser can submit a YouTube URL and see the resolved title, derived query, and stored results.
- No `ContentChunk` is created for a YouTube video before a transcript is manually supplied.
- TXT/VTT/SRT transcript input is normalized and creates persisted chunks.
- Topic memberships and circles update after transcript ingestion.
- Chat answers show sources or explicitly refuse to answer.
- Configured academic APIs appear in the chat discovery trace, and API metadata never creates `ContentChunk` rows by itself.
- Uploaded journals/books with extractable PDF or DOCX content create persisted chunks and can preview safely in chat.
- The full Django test suite and migration check pass.
