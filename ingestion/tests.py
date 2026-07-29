from unittest.mock import patch

from django.test import TestCase

from ingestion.services.providers import discover_external_content, search_openalex


class ProviderDiscoveryTests(TestCase):
    @patch("ingestion.services.providers._get_json")
    def test_openalex_handles_nullable_locations(self, mock_get_json):
        mock_get_json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "title": "Systems Thinking Foundations",
                    "publication_year": 2023,
                    "doi": "10.1000/example",
                    "content": None,
                    "primary_location": None,
                    "best_oa_location": None,
                    "authorships": [],
                    "abstract_inverted_index": {},
                }
            ]
        }

        results = search_openalex("systems thinking", per_page=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Systems Thinking Foundations")
        self.assertEqual(results[0]["license"], "")
        self.assertTrue(results[0]["pdf_url"].endswith("/W123.pdf"))

    @patch("ingestion.services.providers.search_semantic_scholar", side_effect=RuntimeError("provider blew up"))
    @patch("ingestion.services.providers.search_crossref", return_value=[])
    def test_discovery_survives_unexpected_provider_errors(self, mock_crossref, mock_semantic):
        payload = discover_external_content(
            "systems thinking",
            limit_per_provider=1,
            selected_providers=["Crossref", "Semantic Scholar"],
        )

        statuses = {item["name"]: item for item in payload["providers"]}
        self.assertEqual(statuses["Crossref"]["status"], "ok")
        self.assertEqual(statuses["Semantic Scholar"]["status"], "unavailable")
        self.assertIn("RuntimeError", statuses["Semantic Scholar"]["message"])
