from django.core.management.base import BaseCommand

from core.services.warmup import warmup_systems_thinking_cache


class Command(BaseCommand):
    help = "Warm systems thinking cache entries used by the chatbot."

    def handle(self, *args, **options):
        entries = warmup_systems_thinking_cache()
        self.stdout.write(self.style.SUCCESS(f"Warmed {len(entries)} systems thinking cache entries."))
