from django import forms

from .models import AssessmentQuestion


class AssessmentSubmissionForm(forms.Form):
    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = questions or []
        for question in self.questions:
            field_name = f"question_{question.pk}"
            if question.question_type == AssessmentQuestion.QuestionType.MULTIPLE_CHOICE:
                choices = [(option, option) for option in question.options]
                self.fields[field_name] = forms.ChoiceField(
                    label=question.prompt,
                    choices=choices,
                    widget=forms.RadioSelect,
                )
            else:
                self.fields[field_name] = forms.CharField(
                    label=question.prompt,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
