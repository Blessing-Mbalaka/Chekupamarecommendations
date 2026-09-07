from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.services import gemini, llm, ollama


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

    @patch("recommendations.services.llm.gemini.is_configured", return_value=False)
    @patch("recommendations.services.llm.ollama.is_available", return_value=True)
    @patch("recommendations.services.llm.ollama.generate_text", return_value="A grounded response.")
    def test_chat_generation_uses_configured_ollama_timeout(
        self,
        mock_generate_text,
        mock_is_available,
        mock_is_configured,
    ):
        response, backend = llm.generate_chat_text("Use sources only.", ["Question", "Sources"])

        self.assertEqual(response, "A grounded response.")
        self.assertEqual(backend, "ollama")
        self.assertEqual(
            mock_generate_text.call_args.kwargs["timeout_seconds"],
            ollama.OLLAMA_TEXT_TIMEOUT,
        )
        self.assertEqual(
            mock_generate_text.call_args.kwargs["model"],
            ollama.OLLAMA_TEXT_MODEL,
        )


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

    @patch("recommendations.services.ollama.is_available", return_value=True)
    @patch("recommendations.services.ollama._post_json")
    def test_embed_texts_batches_inputs(self, mock_post_json, mock_is_available):
        mock_post_json.side_effect = [
            {"embeddings": [[0.1], [0.2]]},
            {"embeddings": [[0.3]]},
        ]

        embeddings = ollama.embed_texts(["one", "two", "three"], batch_size=2)

        self.assertEqual(embeddings, [[0.1], [0.2], [0.3]])
        self.assertEqual(mock_post_json.call_count, 2)

    @patch("recommendations.services.ollama.request.urlopen")
    def test_generate_text_stream_yields_incremental_tokens(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = [
            b'{"response":"Feedback","done":false}\n',
            b'{"response":" loops","done":false}\n',
            b'{"response":"","done":true}\n',
        ]

        tokens = list(
            ollama.generate_text_stream(
                "Use sources.",
                "Explain loops.",
                model="ministral-3:3b",
                timeout_seconds=10,
            )
        )

        self.assertEqual(tokens, ["Feedback", " loops"])


class GeminiServiceTests(SimpleTestCase):
    @patch("recommendations.services.gemini.is_configured", return_value=True)
    @patch("recommendations.services.gemini._post_json")
    def test_embed_texts_batches_inputs(self, mock_post_json, mock_is_configured):
        mock_post_json.side_effect = [
            {"embeddings": [{"values": [0.1]}, {"values": [0.2]}]},
            {"embeddings": [{"values": [0.3]}]},
        ]

        embeddings = gemini.embed_texts(["one", "two", "three"], batch_size=2)

        self.assertEqual(embeddings, [[0.1], [0.2], [0.3]])
        self.assertEqual(mock_post_json.call_count, 2)
