# Recommendation Engine

An API-first Django learning support platform with:

- personalized student profiles and free-text learning challenges
- baseline assessments authored by lecturers
- uploaded and external learning materials
- a chatbot that can use Gemini when configured
- recommendation bubbles linked to validated materials
- analytics for page views, clicks, material views, and dwell time

## Current Capabilities

- Login flow and role-aware navigation
- Student profile management with large free-text `challenges`
- Course, topic, material, baseline assessment, and lecturer prompt models
- Internal vs external material separation
- Original source storage metadata for external resources
- Chat persistence with personalized recommendation responses
- Gemini integration hooks for text generation and embeddings
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
- YouTube: this app currently treats YouTube as manual-only. Known URLs can be stored and embedded without using the YouTube Data API.
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
