from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from ingestion.services.vector_store import CHUNKING_STRATEGY, index_material, material_source_text
from learning.models import Material


class Command(BaseCommand):
    help = "Rebuild RAG chunks and embeddings for validated materials that have full text."

    def add_arguments(self, parser):
        parser.add_argument("--course", help="Restrict to a course code.")
        parser.add_argument("--material-id", type=int, help="Restrict to one material.")
        parser.add_argument("--dry-run", action="store_true", help="List eligible materials without changing chunks.")

    def handle(self, *args, **options):
        full_text_evidence = (
            ~Q(file="")
            | Q(content_chunks__isnull=False)
            | Q(research_videos__transcript__gt="")
            | Q(source_endpoint__icontains="transcript")
            | Q(
                source_origin=Material.SourceOrigin.INTERNAL,
                source_type=Material.SourceType.FILE,
                source_provider__istartswith="Uploaded",
            )
        )
        materials = (
            Material.objects.filter(is_validated=True)
            .filter(full_text_evidence)
            .exclude(semantic_text="", file="")
            .select_related("course")
            .distinct()
        )
        if options["course"]:
            materials = materials.filter(course__code=options["course"])
        if options["material_id"]:
            materials = materials.filter(pk=options["material_id"])
        materials = list(materials.order_by("pk"))
        if not materials:
            raise CommandError("No validated, content-bearing materials matched.")

        if options["dry_run"]:
            for material in materials:
                self.stdout.write(f"{material.pk}: {material.course.code} / {material.title}")
            self.stdout.write(
                self.style.SUCCESS(f"{len(materials)} material(s) eligible for {CHUNKING_STRATEGY}.")
            )
            return

        total_chunks = 0
        failed = 0
        for material in materials:
            source_text = material_source_text(material)
            if not source_text.strip():
                failed += 1
                self.stderr.write(f"Skipped {material.pk}: no extractable text ({material.title})")
                continue
            try:
                chunks = index_material(material, text=source_text)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"Failed {material.pk} ({material.title}): {exc}")
                continue
            total_chunks += len(chunks)
            self.stdout.write(f"Indexed {material.pk}: {len(chunks)} chunks ({material.title})")

        self.stdout.write(
            self.style.SUCCESS(
                f"RAG reindex complete: {len(materials) - failed} material(s), "
                f"{total_chunks} chunks, {failed} skipped/failed."
            )
        )
