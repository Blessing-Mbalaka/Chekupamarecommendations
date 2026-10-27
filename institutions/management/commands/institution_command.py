import argparse
from django.core.management import BaseCommand, CommandError, call_command
from institutions.models import Institution
from institutions.tenancy import institution_context

class Command(BaseCommand):
    help = 'Run a data command within one institution boundary.'
    def add_arguments(self, parser):
        parser.add_argument('institution_code')
        parser.add_argument('command')
        parser.add_argument('arguments', nargs=argparse.REMAINDER)
    def handle(self, institution_code, command, arguments, **options):
        if command in {'institution_command', 'migrate', 'makemigrations', 'flush', 'test', 'runserver'}:
            raise CommandError('This wrapper is for institution data commands only.')
        try:
            institution = Institution.objects.get(slug=institution_code, is_active=True)
        except Institution.DoesNotExist:
            raise CommandError('Choose an active institution code.')
        with institution_context(institution):
            call_command(command, *arguments, stdout=self.stdout, stderr=self.stderr)
