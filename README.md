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

Set these environment variables before running the app if you want Gemini-backed responses and embeddings:

```powershell
$env:GEMINI_API_KEY="your-key"
$env:GEMINI_TEXT_MODEL="gemini-3.6-flash"
$env:GEMINI_EMBED_MODEL="gemini-embedding-2"
```

If `GEMINI_API_KEY` is missing, the chatbot still works using the local recommendation fallback.

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
