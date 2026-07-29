from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.services import llm, ollama


class LlmBackendTests(SimpleTestCase):
    @patch("recommendations.services.llm.gemini.is_configured", return_value=True)
    @patch("recommendations.services.llm.gemini.generate_text", return_value="calculus derivatives beginner video")
    def test_refine_search_query_prefers_gemini(self, mock_generate_text, mock_is_configured):
        query, backend = llm.refine_search_query("help me with derivatives", "I struggle with basics")

        self.assertEqual(query, "calculus derivatives beginner video")
        self.assertEqual(backend, "gemini")

    @patch("recommendations.services.llm.gemini.is_configured", return_value=False)
    @patch("recommendations.services.llm.ollama.is_available", return_value=True)
    @patch("recommendations.services.llm.ollama.generate_text", return_value="physics motion worked examples")
    def test_refine_search_query_falls_back_to_ollama(self, mock_generate_text, mock_is_available, mock_is_configured):
        query, backend = llm.refine_search_query("easy physics examples")

        self.assertEqual(query, "physics motion worked examples")
        self.assertEqual(backend, "ollama")


class OllamaServiceTests(SimpleTestCase):
    @patch("recommendations.services.ollama._get_json")
    def test_list_models_returns_local_models(self, mock_get_json):
        mock_get_json.return_value = {
            "models": [
                {"name": "ministral-3:3b"},
                {"name": "nomic-embed-text:latest"},
                {"name": "tinyllama:latest"},
            ]
        }

        models = ollama.list_models()

        self.assertEqual([model["name"] for model in models], ["ministral-3:3b", "nomic-embed-text:latest", "tinyllama:latest"])
