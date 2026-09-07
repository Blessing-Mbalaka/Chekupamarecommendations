#when deploying
so the pdfs or embedded uploads are in gitignore so you might want to chunk them on the deployed with fresh database since github cant handle big files.

# Recommendation Engine

An API-first Django learning support platform with:

- personalized student profiles and free-text learning challenges
- baseline assessments authored by lecturers
- uploaded and external learning materials
- a retrieval-only chatbot grounded in stored vector chunks
- recommendation bubbles linked to validated materials
- analytics for page views, clicks, material views, and dwell time

## Current Capabilities

- Login flow and role-aware navigation
- UJ-branded responsive interface using the official open-access university logo
- Student profile management with large free-text `challenges`
- Course, topic, material, baseline assessment, and lecturer prompt models
- Internal vs external material separation
- Original source storage metadata for external resources
- Chat persistence with personalized recommendation responses
- YouTube title-derived research with top-video metadata collection
- Manual transcript upload/paste, cleaning, chunking, and embedding
- Single-surface ChatGPT-style conversation with inline YouTube/PDF source previews
- LDA/optional BERTopic theme extraction with overlapping cluster visualization
- Gemini integration hooks for grounded generation and embeddings
- Fallback rule-based recommendations when Gemini is not configured
- Analytics tracking middleware and event endpoint
- Django admin support for managing users, courses, materials, ingestion, and analytics

## Gemini Setup

Copy `.env.example` to `.env` and fill in the values you want to use.

```powershell
Copy-Item .env.example .env
```

The app now auto-loads `.env` on startup. These are the main values:

```powershell
GEMINI_API_KEY=your-key
GEMINI_TEXT_MODEL=gemini-3.6-flash
GEMINI_EMBED_MODEL=gemini-embedding-2
OLLAMA_BASE_URL=http://localhost:11434/api
OLLAMA_TEXT_MODEL=ministral-3:3b
OLLAMA_EMBED_MODEL=nomic-embed-text:latest
```

If `GEMINI_API_KEY` is missing, the chatbot still works using the local recommendation fallback.
If Ollama is running locally, the chatbot can also fall back to your local models for refinement, response generation, and embeddings.

The chat request path is intentionally kept fast:
- provider calls are bounded by short per-provider timeouts
- provider discovery has a global time budget
- chat recommendations skip expensive on-the-fly embedding generation

## Other API Notes

- OpenAlex: free and a strong default choice for academic discovery. Current docs indicate API keys are now required for API usage, and an email is still useful for identification.
- Crossref: free and useful for DOI and paper metadata lookup.
- Semantic Scholar: useful for paper discovery; an API key is optional for low-volume usage but worth supporting.
- Springer Nature: supported as an external provider using `api.springernature.com` endpoints. Current official docs show `meta/v2`, `metadata`, `openaccess`, and full-text/TDM paths under that host.
- Google Scholar (SerpApi): supported through the maintained `serpapi` Python SDK using `engine=google_scholar`. Set `SERPAPI_API_KEY` (or `SERPAPI_KEY`); chat displays every fetched result as a numbered external link while keeping it outside answer evidence until full text is indexed.
- SerpApi YouTube fallback: when configured, `engine=youtube` can supply video discovery and `engine=youtube_video_transcript` can fetch English transcripts for existing or newly researched videos. Teaching staff must trigger transcript ingestion; successful transcripts are indexed into RAG with provider provenance.

## Quiz workflow

- Lecturers, teaching assistants, and administrators have a dedicated Quiz Builder.
- Questions can be created manually or generated as editable JSON drafts from selected indexed course materials.
- AI drafts are labelled with their generation backend and must be reviewed before publishing.
- Students can take published quizzes assigned to their enrolled courses and receive question-level results.
- Quiz attempts and answers are persisted separately from baseline assessments.
- YouTube: set `YOUTUBE_API_KEY` to resolve a seed title, search related videos, and store metadata. Transcript ingestion remains manual by design; metadata-only videos are excluded from chatbot RAG.
- Scopus: usually commercial or institution-gated, so I have left it as a future connector rather than a default path.

## Run Locally

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Test

```powershell
python manage.py test
```

## External Discovery Providers

The service layer includes normalized search helpers for:

- OpenAlex
- Crossref
- Semantic Scholar

These are implemented in [ingestion/services/providers.py](/C:/Users/Bjmba/Desktop/Python%20WebApps/ReccomendationEngine/ingestion/services/providers.py).

## Next Expansion Areas

- lecturer UI beyond Django admin for resource discovery and approvals
- site download and deeper document extraction for RAG pipelines
- Playwright browser automation for end-to-end UI testing
- background jobs for embedding refresh and external paper archiving
