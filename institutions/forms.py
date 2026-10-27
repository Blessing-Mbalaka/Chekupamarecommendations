from django import forms
from django.contrib.auth.forms import UserCreationForm
from accounts.models import User
from learning.models import Course, Topic
from .models import Institution, Department

class InstitutionRegistrationForm(UserCreationForm):
    institution_name = forms.CharField(max_length=200)
    institution_code = forms.SlugField(max_length=60)
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

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code']
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
