from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.temp_functions.commonquestions import warm_common_question_cache
from learning.models import Course


class Command(BaseCommand):
    help = "Warm cache entries for common markdown questions using the grounded chat pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--path", default="", help="Optional path to the markdown file containing common questions.")
        parser.add_argument("--course-code", default="", help="Optional course code used to scope retrieval.")
        parser.add_argument("--course-id", type=int, default=0, help="Optional course id used to scope retrieval.")
        parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of questions to warm.")

    def handle(self, *args, **options):
        course = None
        if options["course_id"]:
            course = Course.objects.filter(pk=options["course_id"]).first()
            if not course:
                raise CommandError(f"No course found for id {options['course_id']}.")
        elif options["course_code"]:
            course = Course.objects.filter(code__iexact=options["course_code"]).first()
            if not course:
                raise CommandError(f"No course found for code {options['course_code']}.")

        source_path = Path(options["path"]).expanduser() if options["path"] else None
        if source_path and not source_path.exists():
            raise CommandError(f"Question file does not exist: {source_path}")

        warmed_entries = warm_common_question_cache(
            path=source_path,
            course=course,
            limit=options["limit"] or None,
        )
        grounded_count = sum(1 for entry in warmed_entries if entry["grounded"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Warmed {len(warmed_entries)} common questions with {grounded_count} grounded responses."
            )
        )