"""Isolated, deterministic settings for local automated tests only."""
import os

os.environ['GEMINI_API_KEY'] = ''
os.environ['OLLAMA_BASE_URL'] = 'http://127.0.0.1:1/api'
os.environ['OLLAMA_TAGS_TIMEOUT_SECONDS'] = '0.1'
os.environ['OLLAMA_TEXT_TIMEOUT_SECONDS'] = '0.1'
os.environ['OLLAMA_EMBED_TIMEOUT_SECONDS'] = '0.1'
from .settings import *  # noqa: F403

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
