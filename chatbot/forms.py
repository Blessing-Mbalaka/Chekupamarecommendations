from django import forms


class ChatMessageForm(forms.Form):
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Ask a question about your course, challenges, or what to study next.",
            }
        )
    )
