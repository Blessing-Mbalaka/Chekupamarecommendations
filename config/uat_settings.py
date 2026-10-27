"""Isolated settings used by the local Playwright UAT suite."""
import os
from pathlib import Path

os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENALEX_API_KEY"] = ""
os.environ["SEMANTIC_SCHOLAR_API_KEY"] = ""
os.environ["SPRINGER_API_KEY"] = ""
os.environ["SERPAPI_API_KEY"] = ""
os.environ["SERPAPI_KEY"] = ""
os.environ["YOUTUBE_API_KEY"] = ""
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1/api"
os.environ["OLLAMA_TAGS_TIMEOUT_SECONDS"] = "0.1"
os.environ["OLLAMA_TEXT_TIMEOUT_SECONDS"] = "0.1"
os.environ["OLLAMA_EMBED_TIMEOUT_SECONDS"] = "0.1"

from .settings import *  # noqa: F403

UAT_ROOT = Path(os.getenv("UAT_ROOT", BASE_DIR / ".uat"))  # noqa: F405
UAT_ROOT.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": UAT_ROOT / "uat.sqlite3",
    }
}
MEDIA_ROOT = UAT_ROOT / "media"
STATIC_ROOT = UAT_ROOT / "staticfiles"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
