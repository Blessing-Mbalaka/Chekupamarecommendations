# Methodology

UJ Learning Navigator: a course-scoped Retrieval-Augmented Generation (RAG) study assistant with a heuristic, profile-aware recommendation engine.

## 1. Objective

Give each student a study assistant that:

1. answers questions **only from the validated material of the course they are working in**;
2. recommends further reading and videos suited to the student's profile and recent performance;
3. lets lecturers, teaching assistants and administrators manage users and material per course, with full control over what the assistant can retrieve.

## 2. System architecture

| Layer | Implementation |
|-------|----------------|
| Framework | Django (server-rendered templates, SQLite in development) |
| Apps | `accounts` (users, roles, student profile), `core` (dashboard, management UI, error handling), `ingestion` (materials, chunking, vector store), `chatbot` (RAG chat), `recommendations`, `learning` (assessments, dashboard), `analytics_app` (events) |
| LLM / embeddings | Gemini (`GEMINI_TEXT_MODEL`, `GEMINI_EMBED_MODEL`, configured in `config/settings.py`), with a fallback when no embedding is available |
| Static / media | WhiteNoise for static files; media served through Django |

## 3. Users, roles and course scoping

- Roles: student, lecturer, teaching assistant, administrator. Each is tied to one or more courses.
- A student's chat is bound to an **active course**, chosen through a course picker modal on the chat page. Chats are logged per course.
- Course scoping was implemented **without schema migrations**, reusing existing relations between users, courses and materials, so existing data is untouched.
- Staff manage accounts at `/manage/` (user CRUD, activation/deactivation, per-course role assignment). Lecturers see and manage their own courses' material; administrators see all.
- Deactivated accounts cannot sign in and are told so explicitly ("deactivated and awaiting activation"). The message is shown only when the password is correct, so usernames cannot be enumerated.

## 4. Content ingestion and indexing

1. **Upload / import**: lecturers and admins add materials (documents, papers, videos) to a course. Only **validated** materials are eligible for retrieval and recommendation.
2. **Text extraction**: `material_source_text` builds the indexable text from the file and its metadata.
3. **Chunking**: strategy `semantic-cohesion-v1` (`ingestion/services/vector_store.py`) splits documents into cohesive chunks stored as `ContentChunk` rows, each recording its chunking strategy and embedding model.
4. **Embedding**: each chunk is embedded with the configured embedding model (batched via `embed_texts`) and stored with the chunk.
5. **Re-indexing**: the `reindex_rag` management command rebuilds chunks when the strategy or model changes.
6. **Chunk management**: chunks can be viewed and deleted from the management UI (`templates/manage/chunk_list.html`) so poor or unwanted passages can be removed without deleting the material.

## 5. Retrieval-Augmented chat

1. The question is classified as a standalone question or a **follow-up** (`_is_follow_up`). Follow-ups are expanded with recent conversation so retrieval is not lost on pronouns such as "it" or "that".
2. The query is embedded and compared by similarity against chunks **filtered to the active course** (`retrieve_chunks`), with lexical signals as support.
3. The top chunks are placed in the prompt as numbered sources.
4. The system prompt instructs the model to act as a retrieval-only course assistant: answer from the supplied excerpts and say so when they do not contain the answer.
5. Answers are cached for five minutes, keyed per question and course.
6. After each answer, the top retrieved materials are stored as recommendations linked to the message.

Why this design: restricting retrieval to a course boundary is the main control against off-topic or cross-course answers; retrieval-only prompting limits hallucination.

## 6. Recommendation engine

`recommend_for_student` (`recommendations/services/engine.py`) is a transparent heuristic ranker, not a trained model.

**Inputs**
- Student profile text: `challenges`, `goals`, `identifiers`, plus the optional current query.
- Weak topics: topics of questions answered incorrectly in the student's last 5 assessment attempts.
- Candidate set: validated materials, optionally restricted to a course.

**Score per material**

| Signal | Contribution |
|--------|--------------|
| Each profile/query token found in title, description, tags, provider, citation, topic or course title | +3 |
| Each weak-topic token found in the material | +5 |
| Has a publication year | +1 |
| Paper or video | +1.5 |
| External origin | +0.5 |
| Cosine similarity of profile embedding and material embedding (when available; cached on the material) | up to ×10 |

Materials are ranked by score and the top N returned (4 on the dashboard). If nothing scores above zero, the first N validated materials are returned. Results are persisted as `Recommendation` rows.

## 7. Personalisation: current state and limits

- **Personalised:** the dashboard recommendations and the recommendations stored after chat, via the profile, weak topics and semantic similarity above.
- **Not personalised:** the chatbot prompt. The system instruction is identical for all students; profile goals, challenges and quiz weaknesses are not sent to the model.
- **Limits:** weak topics are matched by words, not mastery level; the stored recommendation reason is a fixed string; there is no minimum retrieval score threshold.

Planned improvement (not yet implemented): inject a short profile and weak-topics note that adjusts tone and examples only (never overriding "answer only from sources"), include the profile in the cache key, and store the actual matched signal as the recommendation reason.

## 8. Security and production hardening

- `DEBUG` is read from `DJANGO_DEBUG` and defaults to `False`.
- Custom 400, 403, 404, 500 and CSRF-failure pages (`core/error_views.py`, `templates/errors/error.html`). A stale login page (a common cause of CSRF failure when signing in from several browsers) redirects back to a fresh login with a friendly message.
- WhiteNoise serves static files; `collectstatic` must be run after CSS changes.
- Sidebar navigation is never rendered on login pages.
- Outstanding: replace the hard-coded `SECRET_KEY` and correct `DJANGO_ALLOWED_HOSTS` before deployment.

## 9. Evaluation and testing

- **Automated tests:** Django test suites for chatbot, ingestion (chunking, retrieval), core (management UI, error pages), accounts (deactivated login) and learning. The most recent full run passed (90 tests before the later additions; targeted runs of the later additions also passed).
- **Run:** `.\.venv\Scripts\python.exe manage.py test chatbot ingestion core learning accounts`
- **Manual checks still required:** browser verification of the management pages, error pages and login layout.

### Proposed outcome evaluation
There is currently no measure of personalisation effectiveness. Suggested metrics, using events already collected by `analytics_app`:

1. Recommendation click-through rate and dwell time.
2. Helpful / not-helpful feedback on answers and recommendations.
3. Change in assessment scores on topics after related recommendations were opened.
4. Retrieval quality: a labelled set of course questions, scoring whether the expected source chunk appears in the top k.
5. Isolation check: confirm that questions for course A never cite course B material.

## 10. Limitations

- Keyword-based scoring may miss synonyms; the embedding term only partly compensates.
- Quality depends on the validated material and chunk quality of each course.
- LLM output can still err within the supplied sources; answers should cite their sources.
- Personalisation is limited to recommendation ranking until prompt personalisation is added.
