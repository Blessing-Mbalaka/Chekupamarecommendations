from django import forms

from learning.models import Course, Material, Topic


class MaterialUploadForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            "course",
            "topic",
            "title",
            "description",
            "publication_year",
            "source_type",
            "file",
            "external_url",
            "youtube_title",
            "tags",
        ]


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
