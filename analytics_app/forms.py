from django import forms

from learning.models import Course

from .models import QuestionTheme


class QuestionThemeForm(forms.ModelForm):
    class Meta:
        model = QuestionTheme
        fields = ("course", "label", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, courses=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = courses if courses is not None else Course.objects.none()


class TopicModelForm(forms.Form):
    course = forms.ModelChoiceField(queryset=Course.objects.none())
    model = forms.ChoiceField(choices=(("lda", "LDA"), ("bertopic", "BERTopic"), ("kmeans", "K-means")))
    theme_count = forms.IntegerField(min_value=2, max_value=10, initial=5, help_text="Choose K for LDA or K-means.")

    def __init__(self, *args, courses=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = courses if courses is not None else Course.objects.none()
