from django import forms

from learning.models import Course, Material, Topic


class MaterialUploadForm(forms.ModelForm):
    ATTRIBUTION_REQUIREMENTS = {
        Material.SourceType.PAPER: ("authors",),
        Material.SourceType.JOURNAL: ("authors", "journal_name"),
        Material.SourceType.BOOK: ("authors", "publisher"),
    }
    URL_REQUIRED_TYPES = {
        Material.SourceType.WEBSITE,
        Material.SourceType.VIDEO,
        Material.SourceType.BLOG,
    }
    LINK_ONLY_TYPES = URL_REQUIRED_TYPES
    DOCUMENT_PREVIEW_TYPES = {
        Material.SourceType.PAPER,
        Material.SourceType.JOURNAL,
        Material.SourceType.BOOK,
        Material.SourceType.OTHER,
    }

    class Meta:
        model = Material
        fields = [
            "course",
            "topic",
            "title",
            "description",
            "publication_year",
            "authors",
            "publisher",
            "journal_name",
            "volume_issue",
            "doi",
            "isbn",
            "source_type",
            "file",
            "external_url",
            "source_preview_url",
            "youtube_title",
            "tags",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs["accept"] = ".pdf,.docx,.txt,.md"
        self.fields["file"].help_text = "Required for Uploaded File. Accepted: PDF, DOCX, TXT, or Markdown."
        self.fields["external_url"].help_text = "Required for websites, videos, and blog posts."
        self.fields["source_preview_url"].label = "Document preview URL"
        self.fields["source_preview_url"].help_text = (
            "Optional for paper, journal, book, or other document sources. Use a direct PDF URL or same-origin preview URL."
        )
        self.fields["youtube_title"].help_text = "Optional for video materials. Leave blank if the URL already identifies the video."
        self.fields["doi"].help_text = "Optional; leave blank when the publication has no DOI."
        self.fields["isbn"].help_text = "Optional; leave blank when the book has no ISBN."

    def clean(self):
        cleaned = super().clean()
        course = cleaned.get("course")
        topic = cleaned.get("topic")
        if course and topic and topic.course_id != course.pk:
            self.add_error("topic", "Choose a topic that belongs to the selected course.")
        source_type = cleaned.get("source_type")
        uploaded_file = cleaned.get("file")
        external_url = (cleaned.get("external_url") or "").strip()
        source_preview_url = (cleaned.get("source_preview_url") or "").strip()
        youtube_title = (cleaned.get("youtube_title") or "").strip()

        if source_type == Material.SourceType.FILE and not uploaded_file:
            self.add_error("file", "Upload a PDF, DOCX, TXT, or Markdown file for this content type.")
        elif source_type in self.URL_REQUIRED_TYPES and not external_url:
            self.add_error("external_url", "Provide the source URL for this content type.")
        elif source_type not in self.URL_REQUIRED_TYPES | {Material.SourceType.FILE} and not uploaded_file and not external_url:
            self.add_error("file", "Upload a file or provide an external URL.")

        if source_type == Material.SourceType.FILE:
            if external_url:
                self.add_error("external_url", "Uploaded File is for local documents only. Use Website, Video, or Blog for links.")
            if source_preview_url:
                self.add_error("source_preview_url", "Document preview URL is only for external document sources.")
            if youtube_title:
                self.add_error("youtube_title", "YouTube title is only used for video materials.")
        elif source_type in self.LINK_ONLY_TYPES:
            if uploaded_file:
                message = "This content type uses an external URL instead of an uploaded file."
                if source_type == Material.SourceType.VIDEO:
                    message = "Video materials use a URL here. Upload transcript text or a transcript file in the YouTube research section instead."
                self.add_error("file", message)
            if source_preview_url:
                self.add_error("source_preview_url", "Document preview URL is only for document-based sources.")
            if source_type != Material.SourceType.VIDEO and youtube_title:
                self.add_error("youtube_title", "YouTube title is only used for video materials.")
        elif source_type not in self.DOCUMENT_PREVIEW_TYPES and source_preview_url:
            self.add_error("source_preview_url", "Document preview URL is only for document-based sources.")

        if source_type != Material.SourceType.VIDEO and not self.errors.get("youtube_title"):
            cleaned["youtube_title"] = ""
        if source_type not in self.DOCUMENT_PREVIEW_TYPES and not self.errors.get("source_preview_url"):
            cleaned["source_preview_url"] = ""

        for field_name in self.ATTRIBUTION_REQUIREMENTS.get(source_type, ()):
            if not cleaned.get(field_name):
                self.add_error(field_name, "This field is required for the selected content type.")
        return cleaned


class DiscoverySearchForm(forms.Form):
    PROVIDER_CHOICES = [
        ("OpenAlex", "OpenAlex"),
        ("Crossref", "Crossref"),
        ("Semantic Scholar", "Semantic Scholar"),
        ("Springer Nature", "Springer Nature"),
        ("Google Scholar (SerpApi)", "Google Scholar (SerpApi)"),
    ]

    query = forms.CharField(
        label="Search query",
        widget=forms.TextInput(
            attrs={"placeholder": "systems thinking journals, causal loop diagrams, leverage points"}
        ),
    )
    course = forms.ModelChoiceField(queryset=Course.objects.all())
    topic = forms.ModelChoiceField(queryset=Topic.objects.select_related("course").all(), required=False)
    providers = forms.MultipleChoiceField(
        choices=PROVIDER_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        initial=[choice[0] for choice in PROVIDER_CHOICES],
    )
    limit_per_provider = forms.IntegerField(min_value=1, max_value=5, initial=2)


class YouTubeResearchForm(forms.Form):
    seed_url = forms.URLField(
        label="YouTube seed URL",
        widget=forms.URLInput(attrs={"placeholder": "https://www.youtube.com/watch?v=..."}),
    )
    course = forms.ModelChoiceField(queryset=Course.objects.all())
    topic = forms.ModelChoiceField(queryset=Topic.objects.select_related("course").all(), required=False)
    video_count = forms.IntegerField(label="Top videos", min_value=2, max_value=25, initial=10)
    theme_count = forms.IntegerField(label="Theme clusters", min_value=2, max_value=10, initial=5)
    topic_model = forms.ChoiceField(
        choices=[("lda", "LDA"), ("bertopic", "BERTopic (when installed)")], initial="lda"
    )

    def clean(self):
        cleaned = super().clean()
        course = cleaned.get("course")
        topic = cleaned.get("topic")
        if course and topic and topic.course_id != course.pk:
            self.add_error("topic", "Choose a topic that belongs to the selected course.")
        return cleaned


class TranscriptUploadForm(forms.Form):
    transcript_file = forms.FileField(required=False, help_text="TXT, VTT, or SRT")
    transcript_text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 5}))

    def clean(self):
        cleaned = super().clean()
        transcript_file = cleaned.get("transcript_file")
        if transcript_file and transcript_file.size > 5 * 1024 * 1024:
            self.add_error("transcript_file", "Transcript files must be 5 MB or smaller.")
        if not transcript_file and not cleaned.get("transcript_text", "").strip():
            raise forms.ValidationError("Upload a transcript file or paste transcript text.")
        return cleaned
