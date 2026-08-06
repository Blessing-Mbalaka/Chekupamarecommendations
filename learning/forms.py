from django import forms

from .models import AssessmentQuestion, Material, Quiz, QuizQuestion


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


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["course", "title", "description", "instructions", "is_published"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "instructions": forms.Textarea(attrs={"rows": 3}),
        }


class QuizQuestionForm(forms.ModelForm):
    options_text = forms.CharField(
        required=False,
        label="Answer options",
        help_text="For multiple choice, enter one option per line.",
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    class Meta:
        model = QuizQuestion
        fields = [
            "source_material", "prompt", "question_type", "correct_answer", "explanation", "points", "order"
        ]
        widgets = {"prompt": forms.Textarea(attrs={"rows": 3}), "explanation": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, quiz=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.quiz = quiz or getattr(self.instance, "quiz", None)
        if self.quiz:
            self.fields["source_material"].queryset = Material.objects.filter(
                course=self.quiz.course, is_validated=True
            )
        if self.instance and self.instance.pk:
            self.fields["options_text"].initial = "\n".join(self.instance.options or [])

    def clean(self):
        cleaned = super().clean()
        options = [line.strip() for line in cleaned.get("options_text", "").splitlines() if line.strip()]
        if cleaned.get("question_type") == QuizQuestion.QuestionType.MULTIPLE_CHOICE:
            if len(options) < 2:
                self.add_error("options_text", "Multiple-choice questions need at least two options.")
            if cleaned.get("correct_answer", "").strip() not in options:
                self.add_error("correct_answer", "The correct answer must exactly match one option.")
        cleaned["options"] = options
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.options = self.cleaned_data.get("options", [])
        if self.quiz:
            instance.quiz = self.quiz
        if commit:
            instance.save()
        return instance


class QuizGenerationForm(forms.Form):
    materials = forms.ModelMultipleChoiceField(
        queryset=Material.objects.none(),
        help_text="Only materials already admitted to the RAG index are available.",
    )
    question_count = forms.IntegerField(min_value=1, max_value=20, initial=5)
    question_type = forms.ChoiceField(
        choices=[("mixed", "Mixed"), *QuizQuestion.QuestionType.choices], initial="mixed"
    )

    def __init__(self, *args, quiz=None, **kwargs):
        super().__init__(*args, **kwargs)
        if quiz:
            self.fields["materials"].queryset = Material.objects.filter(
                course=quiz.course, is_validated=True, content_chunks__isnull=False
            ).distinct()


class QuizSubmissionForm(forms.Form):
    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = questions or []
        for question in self.questions:
            name = f"question_{question.pk}"
            if question.question_type == QuizQuestion.QuestionType.MULTIPLE_CHOICE:
                self.fields[name] = forms.ChoiceField(
                    label=question.prompt,
                    choices=[(option, option) for option in question.options],
                    widget=forms.RadioSelect,
                )
            else:
                self.fields[name] = forms.CharField(
                    label=question.prompt,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
