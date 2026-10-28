from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from accounts.models import User
from learning.models import Course, Topic
from .forms import (
    DepartmentForm,
    InstitutionIdentityForm,
    InstitutionRegistrationForm,
    LecturerApplicationForm,
    ModuleForm,
    StudentRegistrationForm,
    TopicForm,
)
from .models import Institution, Department
from .tenancy import institution_context


def register_institution(request):
    if request.user.is_authenticated:
        return redirect('institutions:course_management')
    form = InstitutionRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            institution = Institution.objects.create(name=form.cleaned_data['institution_name'], slug=form.cleaned_data['institution_code'], email=form.cleaned_data['email'])
            with institution_context(institution):
                user = form.save(commit=False)
                user.institution = institution
                user.role = 'admin'
                user.is_staff = user.is_superuser = False
                user.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('institutions:course_management')
    return render(request, 'institutions/register.html', {'form': form, 'heading': 'Register your institution'})


def register_student(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    form = StudentRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic(), institution_context(form.institution):
            user = form.save(commit=False)
            user.institution = form.institution
            user.role = 'student'
            user.is_staff = user.is_superuser = False
            user.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Account created. Your institution administrator will assign your modules.')
        return redirect('core:dashboard')
    return render(request, 'institutions/register.html', {'form': form, 'heading': 'Join your institution'})


def register_lecturer(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    form = LecturerApplicationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic(), institution_context(form.institution):
            form.save()
        messages.success(
            request,
            'Lecturer application submitted. No email is sent until your institution administrator approves and activates the account.',
        )
        return redirect('login')
    return render(request, 'institutions/lecturer_register.html', {'form': form})


@login_required
def structure(request):
    is_admin = request.user.role == 'admin' or request.user.is_superuser
    if request.user.role == 'lecturer' and not request.user.is_superuser:
        return redirect('institutions:topic_management')
    if not is_admin:
        raise PermissionDenied('Institution administrator access required.')
    edit_kind = request.GET.get('edit')
    edit_id = request.GET.get('id')
    edit_models = {'department': Department, 'module': Course}
    editing = get_object_or_404(edit_models[edit_kind], pk=edit_id) if edit_kind in edit_models and edit_id else None
    department_form = DepartmentForm(prefix='department', instance=editing if edit_kind == 'department' else None)
    module_form = ModuleForm(prefix='module', instance=editing if edit_kind == 'module' else None)
    institution_form = InstitutionIdentityForm(prefix='institution', instance=request.institution)
    departments = Department.objects.prefetch_related('modules__topics')

    def page_context():
        return {
            'is_course_admin': True,
            'institution_form': institution_form,
            'department_form': department_form,
            'module_form': module_form,
            'departments': departments,
        }

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'institution':
            institution_form = InstitutionIdentityForm(
                request.POST,
                prefix='institution',
                instance=request.institution,
            )
            if institution_form.is_valid():
                institution_form.save()
                messages.success(request, 'Institution / faculty details and login code updated.')
                return redirect('institutions:course_management')
            return render(request, 'institutions/structure.html', page_context())
        if action == 'rotate_invite':
            from .models import join_token
            request.institution.join_code = join_token()
            request.institution.save(update_fields=['join_code'])
            messages.success(request, 'Invitation code replaced. The previous code no longer works.')
            return redirect('institutions:course_management')
        choices = {'department': (DepartmentForm, Department), 'module': (ModuleForm, Course)}
        if action not in choices:
            raise PermissionDenied('Unknown action.')
        form_class, model = choices[action]
        record_id = request.POST.get('record_id')
        instance = get_object_or_404(model, pk=record_id) if record_id else None
        form = form_class(request.POST, prefix=action, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, f'{action.title()} saved.')
            return redirect('institutions:course_management')
        if action == 'department': department_form = form
        else: module_form = form
    return render(request, 'institutions/structure.html', page_context())


@login_required
def topic_management(request):
    is_admin = request.user.role == 'admin' or request.user.is_superuser
    is_lecturer = request.user.role == 'lecturer'
    if not is_admin and not is_lecturer:
        raise PermissionDenied('Lecturer or institution administrator access required.')
    available_courses = Course.objects.all() if is_admin else Course.objects.filter(lecturers=request.user)
    editing = None
    if request.GET.get('edit') == 'topic' and request.GET.get('id'):
        editing = get_object_or_404(Topic.objects.filter(course__in=available_courses), pk=request.GET['id'])
    topic_form = TopicForm(prefix='topic', instance=editing, course_queryset=available_courses)
    if request.method == 'POST':
        record_id = request.POST.get('record_id')
        instance = get_object_or_404(Topic.objects.filter(course__in=available_courses), pk=record_id) if record_id else None
        topic_form = TopicForm(request.POST, prefix='topic', instance=instance, course_queryset=available_courses)
        if topic_form.is_valid():
            topic_form.save()
            messages.success(request, 'Topic saved.')
            return redirect('institutions:topic_management')
    return render(request, 'institutions/topic_management.html', {
        'topic_form': topic_form,
        'available_courses': available_courses.prefetch_related('topics'),
        'is_course_admin': is_admin,
    })
