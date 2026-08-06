from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from ingestion.services import providers
from learning.models import Course, Material


class ProviderDiscoveryTests(SimpleTestCase):
    @patch("ingestion.services.providers._get_json")
    def test_openalex_normalizes_results(self, mock_get_json):
        mock_get_json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "title": "Calculus Help",
                    "publication_year": 2024,
                    "primary_location": {"landing_page_url": "https://example.org/paper"},
                    "doi": "10.1000/example",
                    "authorships": [{"author": {"display_name": "Jane Doe"}}],
                    "best_oa_location": {"license": "cc-by"},
                }
            ]
        }

        with patch.object(providers, "OPENALEX_API_KEY", "test-key"):
            results = providers.search_openalex("calculus", per_page=1)

        self.assertEqual(results[0]["source_provider"], "OpenAlex")
        self.assertEqual(results[0]["license"], "cc-by")
        self.assertEqual(results[0]["openalex_work_id"], "W123")
        self.assertEqual(results[0]["pdf_url"], "/learning/materials/openalex/W123/pdf/")

    @patch("ingestion.services.providers.search_openalex")
    @patch("ingestion.services.providers.search_crossref")
    @patch("ingestion.services.providers.search_semantic_scholar")
    @patch("ingestion.services.providers.search_springer")
    def test_discovery_reports_missing_youtube_key(
        self,
        mock_search_springer,
        mock_search_semantic,
        mock_search_crossref,
        mock_search_openalex,
    ):
        mock_search_openalex.return_value = [{"title": "A", "source_provider": "OpenAlex"}]
        mock_search_crossref.return_value = [{"title": "B", "source_provider": "Crossref"}]
        mock_search_semantic.return_value = [{"title": "C", "source_provider": "Semantic Scholar"}]
        mock_search_springer.return_value = []

        with patch.object(providers, "OPENALEX_API_KEY", "test-key"), patch.object(providers, "SPRINGER_API_KEY", ""):
            payload = providers.discover_external_content("limits", limit_per_provider=1)

        statuses = {item["name"]: item["status"] for item in payload["providers"]}
        self.assertEqual(statuses["OpenAlex"], "ok")
        self.assertEqual(statuses["YouTube"], "manual_only")
        self.assertEqual(statuses["Springer Nature"], "missing_key")
        self.assertEqual(len(payload["results"]), 3)

    @patch("ingestion.services.providers._get_json")
    def test_springer_normalizes_results(self, mock_get_json):
        mock_get_json.return_value = {
            "records": [
                {
                    "title": "Linear Algebra in Practice",
                    "doi": "10.1007/test",
                    "identifier": "springer-test-id",
                    "publicationDate": "2025-01-01",
                    "publicationName": "Springer Journal",
                    "creators": [{"creator": "John Smith"}],
                    "url": [
                        {"format": "html", "value": "https://link.springer.com/article/test"},
                        {"format": "pdf", "value": "https://link.springer.com/content/pdf/test.pdf"},
                    ],
                }
            ]
        }
        with patch.object(providers, "SPRINGER_API_KEY", "springer-key"):
            results = providers.search_springer("linear algebra", page_size=1)

        self.assertEqual(results[0]["source_provider"], "Springer Nature")
        self.assertEqual(results[0]["source_record_id"], "springer-test-id")
        self.assertEqual(results[0]["pdf_url"], "https://link.springer.com/content/pdf/test.pdf")

    @patch("ingestion.services.providers.serpapi.Client")
    def test_google_scholar_uses_serpapi_sdk_and_scholar_engine(self, mock_client):
        mock_client.return_value.search.return_value = {
            "organic_results": [
                {
                    "title": "Systems Thinking Research",
                    "link": "https://example.org/systems",
                    "result_id": "scholar-1",
                    "publication_info": {"summary": "A Researcher - Systems Journal, 2025"},
                    "resources": [{"file_format": "PDF", "link": "https://example.org/systems.pdf"}],
                }
            ]
        }

        with patch.object(providers, "SERPAPI_API_KEY", "test-key"):
            results = providers.search_serpapi_scholar("Systems thinking", page_size=10)

        mock_client.assert_called_once_with(api_key="test-key", timeout=providers.PROVIDER_REQUEST_TIMEOUT)
        params = mock_client.return_value.search.call_args.args[0]
        self.assertEqual(params["engine"], "google_scholar")
        self.assertEqual(params["hl"], "en")
        self.assertEqual(params["num"], 10)
        self.assertEqual(results[0]["pdf_url"], "https://example.org/systems.pdf")

    @patch("ingestion.services.providers.serpapi.Client")
    def test_youtube_transcript_uses_serpapi_transcript_engine(self, mock_client):
        mock_client.return_value.search.return_value = {
            "transcript": [
                {"start_ms": 0, "end_ms": 1000, "snippet": "Systems have connected parts."},
                {"start_ms": 1000, "end_ms": 2000, "snippet": "Feedback changes behaviour."},
            ]
        }
        with patch.object(providers, "SERPAPI_API_KEY", "test-key"):
            result = providers.fetch_serpapi_youtube_transcript("video123")

        params = mock_client.return_value.search.call_args.args[0]
        self.assertEqual(params["engine"], "youtube_video_transcript")
        self.assertEqual(params["v"], "video123")
        self.assertIn("Feedback changes behaviour", result["text"])


class ProviderPersistenceTests(TestCase):
    def test_null_provider_text_fields_are_stored_as_empty_strings(self):
        course = Course.objects.create(code="SYS101", title="Systems Thinking")
        payload = {
            "results": [
                {
                    "title": "OpenAlex result without a license",
                    "source_provider": "OpenAlex",
                    "source_record_id": "https://openalex.org/W123",
                    "license": None,
                    "description": None,
                    "authors": None,
                    "original_source_url": None,
                }
            ]
        }

        materials = providers.persist_external_results(payload, course=course)

        self.assertEqual(len(materials), 1)
        material = Material.objects.get(pk=materials[0].pk)
        self.assertEqual(material.tags, "")
        self.assertEqual(material.description, "")
        self.assertEqual(material.authors, "")
        self.assertEqual(material.original_source_url, "")
