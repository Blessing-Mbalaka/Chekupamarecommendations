from unittest.mock import patch

from django.test import TestCase

from ingestion.models import ContentChunk
from ingestion.services.providers import discover_external_content, persist_external_results, search_openalex
from learning.models import Course, Material


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
        self.assertEqual(results[0]["openalex_work_id"], "W123")
        self.assertEqual(results[0]["pdf_url"], "/learning/materials/openalex/W123/pdf/")

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

    def test_persisted_journal_keeps_structure_but_is_not_automatically_indexed(self):
        course = Course.objects.create(code="SYS101", title="Systems Thinking")
        materials = persist_external_results(
            {
                "results": [
                    {
                        "title": "Systems practice",
                        "year": 2025,
                        "source_provider": "Crossref",
                        "source_record_id": "10.1000/systems",
                        "source_type": Material.SourceType.JOURNAL,
                        "external_url": "https://doi.org/10.1000/systems",
                        "pdf_url": "https://example.org/systems.pdf",
                        "authors": "A. Researcher",
                        "journal_name": "Journal of Systems Practice",
                        "publisher": "Example Press",
                        "doi": "10.1000/systems",
                    }
                ]
            },
            course=course,
        )

        material = materials[0]
        self.assertEqual(material.source_type, Material.SourceType.JOURNAL)
        self.assertEqual(material.authors, "A. Researcher")
        self.assertEqual(material.preview_kind, "pdf")
        self.assertFalse(ContentChunk.objects.filter(material=material).exists())
