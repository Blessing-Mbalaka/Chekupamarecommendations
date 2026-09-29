from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from ingestion.models import ContentChunk
from ingestion.services.youtube_research import (
    extract_video_id,
    run_youtube_research,
    store_uploaded_transcript,
    store_serpapi_transcript,
    store_material_serpapi_transcript,
    title_to_research_query,
)
from learning.models import Course


class YouTubeResearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("researcher", "research@example.com", "password123")
        self.course = Course.objects.create(code="AI101", title="Artificial Intelligence")

    def test_extracts_common_youtube_url_shapes(self):
        self.assertEqual(extract_video_id("https://youtu.be/abc123"), "abc123")
        self.assertEqual(extract_video_id("https://www.youtube.com/watch?v=abc123&t=5"), "abc123")
        self.assertEqual(extract_video_id("https://youtube.com/shorts/abc123"), "abc123")

    def test_title_is_cleaned_into_research_query(self):
        self.assertEqual(
            title_to_research_query("Graph Neural Networks Explained (Official Video) [4K]"),
            "Graph Neural Networks",
        )

    @patch("ingestion.services.youtube_research.extract_themes")
    @patch("ingestion.services.youtube_research.search_videos")
    @patch("ingestion.services.youtube_research.resolve_seed_title")
    def test_video_metadata_is_not_rag_indexed_until_manual_transcript(
        self, mock_resolve, mock_search, mock_extract
    ):
        mock_resolve.return_value = ("seed123", "Understanding Neural Networks")
        mock_search.return_value = [
            {
                "youtube_id": "video123",
                "title": "Neural Networks Visually",
                "description": "Layers and training",
                "channel_title": "Learning Lab",
                "published_at": "2026-01-01T00:00:00Z",
                "duration": "PT8M",
                "thumbnail_url": "https://example.com/thumb.jpg",
                "metadata": {},
            }
        ]
        mock_extract.return_value = (
            [{"label": "Networks", "keywords": ["networks", "layers"]}],
            [[1.0]],
            "lda",
        )
        run = run_youtube_research(
            seed_url="https://youtube.com/watch?v=seed123",
            course=self.course,
            topic=None,
            video_count=5,
            theme_count=3,
            topic_model="lda",
            created_by=self.user,
        )
        video = run.videos.get()
        self.assertEqual(video.transcript_status, "awaiting_upload")
        self.assertFalse(video.material.is_validated)
        self.assertFalse(ContentChunk.objects.exists())

        with patch("ingestion.services.vector_store.embed_text", return_value=([0.1, 0.2], "test")), patch(
            "ingestion.services.youtube_research.extract_themes", return_value=mock_extract.return_value
        ):
            store_uploaded_transcript(video, "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nNetworks learn weighted patterns.")

        chunk = ContentChunk.objects.get()
        self.assertEqual(video.content_chunks.count(), 1)
        self.assertIn("Networks learn weighted patterns", chunk.text)

    @patch("ingestion.services.youtube_research.fetch_serpapi_youtube_transcript")
    def test_serpapi_transcript_is_stored_and_indexed(self, mock_fetch):
        mock_fetch.return_value = {
            "text": "Systems thinking connects feedback loops and system behaviour.",
            "segments": [{"snippet": "Systems thinking connects feedback loops and system behaviour."}],
        }
        run = run_youtube_research
        from ingestion.models import ResearchRun, ResearchVideo
        from learning.models import Material

        research_run = ResearchRun.objects.create(
            course=self.course,
            seed_url="https://youtube.com/watch?v=video123",
            seed_video_id="video123",
            seed_title="Systems thinking",
            research_query="Systems thinking",
            created_by=self.user,
        )
        material = Material.objects.create(
            course=self.course,
            title="Systems video",
            source_type=Material.SourceType.VIDEO,
            external_url="https://youtube.com/watch?v=video123",
            is_validated=True,
        )
        video = ResearchVideo.objects.create(
            run=research_run, material=material, youtube_id="video123", title="Systems video"
        )
        with patch("ingestion.services.vector_store.embed_text", return_value=([0.1], "test")):
            store_serpapi_transcript(video)

        video.refresh_from_db()
        self.assertEqual(video.transcript_status, "serpapi")
        self.assertEqual(video.metadata["transcript_provider"], "SerpApi")
        self.assertTrue(ContentChunk.objects.filter(material=material).exists())

    @patch("ingestion.services.youtube_research.fetch_serpapi_youtube_transcript")
    def test_existing_material_video_can_use_serpapi_transcript(self, mock_fetch):
        from learning.models import Material

        material = Material.objects.create(
            course=self.course,
            title="Existing course video",
            source_type=Material.SourceType.VIDEO,
            external_url="https://www.youtube.com/watch?v=current123",
            is_validated=True,
        )
        mock_fetch.return_value = {
            "text": "This existing video explains systems boundaries and feedback loops.",
            "segments": [{"snippet": "This existing video explains systems boundaries and feedback loops."}],
        }
        with patch("ingestion.services.vector_store.embed_text", return_value=([0.2], "test")):
            chunk_count = store_material_serpapi_transcript(material)

        material.refresh_from_db()
        self.assertEqual(chunk_count, 1)
        self.assertIn("systems boundaries", material.semantic_text)
        self.assertEqual(material.source_endpoint, "SerpApi youtube_video_transcript")
