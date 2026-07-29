from django.core.management.base import BaseCommand

from core.services.demo import bootstrap_demo_data


class Command(BaseCommand):
    help = "Create demo users, systems thinking seed content, and warm the cache."

    def handle(self, *args, **options):
        payload = bootstrap_demo_data()
        self.stdout.write(
            self.style.SUCCESS(
                f"Bootstrapped {payload['course']} with users {', '.join(payload['users'])} and {payload['warmup_entries']} warmup cache entries."
            )
        )
