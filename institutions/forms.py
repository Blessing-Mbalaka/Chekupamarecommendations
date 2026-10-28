from django import forms
from django.contrib.auth.forms import UserCreationForm
from accounts.models import User
from learning.models import Course, Topic
from .models import Institution, Department

class InstitutionRegistrationForm(UserCreationForm):
    institution_name = forms.CharField(max_length=200)
    institution_code = forms.SlugField(
        max_length=60,
        label="Institution / faculty code",
        help_text="Create a short, unique login code to give to your lecturers, teaching assistants, and students.",
    )
    email = forms.EmailField()
    class Meta:
        model = User
        fields = ['institution_name', 'institution_code', 'username', 'first_name', 'last_name', 'email']
    def clean_institution_code(self):
        code = self.cleaned_data['institution_code'].lower()
        if Institution.objects.filter(slug__iexact=code).exists():
            raise forms.ValidationError('This institution code is already in use.')
        return code

class StudentRegistrationForm(UserCreationForm):
    invitation_code = forms.CharField(max_length=64)
    email = forms.EmailField()
    class Meta:
        model = User
        fields = ['invitation_code', 'username', 'first_name', 'last_name', 'email', 'student_number']
    def clean_invitation_code(self):
        try:
            self.institution = Institution.objects.get(join_code=self.cleaned_data['invitation_code'].strip(), is_active=True)
        except Institution.DoesNotExist:
            raise forms.ValidationError('Enter a valid institution invitation code.')
        return self.cleaned_data['invitation_code']


class LecturerApplicationForm(forms.ModelForm):
    institution_code = forms.SlugField(
        max_length=60,
        label="Institution / faculty code",
        widget=forms.TextInput(attrs={"placeholder": "e.g. jbs", "autocomplete": "organization"}),
    )
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {
            "username": forms.TextInput(attrs={"placeholder": "e.g. j.smith"}),
            "first_name": forms.TextInput(attrs={"placeholder": "e.g. Jane"}),
            "last_name": forms.TextInput(attrs={"placeholder": "e.g. Smith"}),
            "email": forms.EmailInput(attrs={"placeholder": "e.g. jane.smith@university.ac.za"}),
        }

    def clean_institution_code(self):
        code = self.cleaned_data["institution_code"].strip().lower()
        self.institution = Institution.objects.filter(slug__iexact=code, is_active=True).first()
        if not self.institution:
            raise forms.ValidationError("Enter a valid institution or faculty code.")
        return code

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User._base_manager.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already in use.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User._base_manager.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.institution = self.institution
        user.role = "lecturer"
        user.is_active = False
        user.is_staff = user.is_superuser = False
        user.set_unusable_password()
        if commit:
            user.save()
        return user


class InstitutionIdentityForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ['name', 'slug', 'email']
        labels = {
            'name': 'Institution / faculty name',
            'slug': 'Login code',
            'email': 'Administrative email',
        }
        help_texts = {
            'slug': 'Share this short code with lecturers, teaching assistants, and students for login.',
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Johannesburg Business School'}),
            'slug': forms.TextInput(attrs={'placeholder': 'e.g. jbs'}),
            'email': forms.EmailInput(attrs={'placeholder': 'e.g. admin@jbs.ac.za'}),
        }

    def clean_slug(self):
        code = self.cleaned_data['slug'].strip().lower()
        if Institution.objects.filter(slug__iexact=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This institution or faculty code is already in use.')
        return code

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. School of Business'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g. BUS'}),
        }
    def clean_code(self):
        from .tenancy import current_institution_id
        code = self.cleaned_data['code'].lower()
        if Department.objects.filter(institution_id=current_institution_id(), code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This department code is already in use.')
        return code

class ModuleForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['department', 'code', 'title', 'description']
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': 'e.g. MBA501'}),
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Strategic Management'}),
            'description': forms.Textarea(attrs={'placeholder': 'e.g. Core strategy concepts and their application in modern organizations.', 'rows': 3}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].required = True
    def clean_code(self):
        from .tenancy import current_institution_id
        code = self.cleaned_data['code'].strip()
        if Course.objects.filter(institution_id=current_institution_id(), code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This module code is already in use.')
        return code

class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ['course', 'title', 'description']
        labels = {'course': 'Module'}
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Competitive advantage'}),
            'description': forms.Textarea(attrs={'placeholder': 'e.g. Frameworks for building and sustaining a competitive advantage.', 'rows': 3}),
        }

    def __init__(self, *args, course_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if course_queryset is not None:
            self.fields['course'].queryset = course_queryset
