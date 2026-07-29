from unittest.mock import patch

from django.test import SimpleTestCase

from ingestion.services import providers


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
        self.assertIn("/works/W123.pdf", results[0]["pdf_url"])

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
