from django.core.management.base import BaseCommand, CommandError

from ingestion.services.providers import (
    SERPAPI_API_KEY,
    fetch_serpapi_youtube_transcript,
    search_serpapi_scholar,
    search_serpapi_youtube,
)


class Command(BaseCommand):
    help = "Run safe live smoke tests for configured SerpApi Scholar and YouTube engines."

    def add_arguments(self, parser):
        parser.add_argument("--query", default="Systems thinking")
        parser.add_argument("--video-id", default="")

    def handle(self, *args, **options):
        if not SERPAPI_API_KEY:
            raise CommandError("SERPAPI_API_KEY (or SERPAPI_KEY) is not configured.")
        query = options["query"]
        scholar = search_serpapi_scholar(query, page_size=3, timeout_seconds=15)
        youtube = search_serpapi_youtube(query, page_size=3, timeout_seconds=15)
        self.stdout.write(self.style.SUCCESS(f"Google Scholar: {len(scholar)} structured results"))
        self.stdout.write(self.style.SUCCESS(f"YouTube search: {len(youtube)} structured results"))
        video_id = options["video_id"] or (youtube[0]["youtube_id"] if youtube else "")
        if video_id:
            transcript = fetch_serpapi_youtube_transcript(video_id, timeout_seconds=20)
            self.stdout.write(
                self.style.SUCCESS(
                    f"YouTube transcript: {len(transcript['segments'])} segments, {len(transcript['text'])} characters"
                )
            )
        else:
            self.stdout.write(self.style.WARNING("YouTube transcript skipped: no video was returned."))
