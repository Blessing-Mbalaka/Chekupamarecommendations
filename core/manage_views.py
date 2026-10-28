from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.services.invitations import send_account_setup_email
from ingestion.models import ContentChunk
from ingestion.services.vector_store import index_material, invalidate_retrieval_cache
from learning.models import Course, Material

from .forms_manage import ManagedMaterialForm, ManagedUserForm

User = get_user_model()


def _is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == UserRole.ADMIN)


def _manageable_courses(user):
    if _is_admin(user):
        return Course.objects.all()
    if user.is_authenticated and user.role == UserRole.LECTURER:
        return Course.objects.filter(lecturers=user)
    return Course.objects.none()


def _require_admin(request):
    if not request.user.is_authenticated:
        raise PermissionDenied
    if not _is_admin(request.user):
        raise PermissionDenied("Only administrators can manage users.")


def _require_material_manager(request):
    if not request.user.is_authenticated or not (
        _is_admin(request.user) or request.user.role == UserRole.LECTURER
    ):
        raise PermissionDenied("Only lecturers and administrators can manage materials.")


def _material_queryset(user):
    return Material.objects.select_related("course", "topic").filter(course__in=_manageable_courses(user))


def _course_labels(user):
    courses = {}
    for role, relation in (
        ("Student", "courses_enrolled"),
        ("Lecturer", "courses_taught"),
        ("TA", "courses_supported"),
    ):
        for course in getattr(user, relation).all():
            courses.setdefault(role, []).append(course.code)
    return courses


def user_list_view(request):
    _require_admin(request)
    users = User.objects.all().order_by("role", "username").prefetch_related(
        "courses_enrolled", "courses_taught", "courses_supported"
    )
    role = request.GET.get("role", "")
    course_id = request.GET.get("course", "")
    query = request.GET.get("q", "").strip()
    if role in UserRole.values:
        users = users.filter(role=role)
    if course_id.isdigit():
        users = users.filter(
            Q(courses_enrolled=course_id) | Q(courses_taught=course_id) | Q(courses_supported=course_id)
        ).distinct()
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    rows = [{"user": user, "courses": _course_labels(user)} for user in users]
    return render(
        request,
        "manage/user_list.html",
        {
            "rows": rows,
            "roles": UserRole.choices,
            "courses": Course.objects.order_by("code"),
            "filters": {"role": role, "course": course_id, "q": query},
        },
    )


def user_edit_view(request, pk=None):
    _require_admin(request)
    instance = get_object_or_404(User, pk=pk) if pk else None
    form = ManagedUserForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        is_new = instance is None
        user = form.save()
        messages.success(request, f"Saved {user.username} as {user.get_role_display()}.")
        if form.cleaned_data.get("temporary_password"):
            messages.warning(
                request,
                "Temporary demo password saved. Share it manually and do not reuse it for a production account.",
            )
        elif is_new:
            try:
                send_account_setup_email(user, request)
            except Exception:
                messages.warning(
                    request,
                    "The account was saved, but the invitation could not be sent. Check SMTP settings, then use Send invite/reset.",
                )
            else:
                messages.success(request, f"Sent a secure account-setup link to {user.email}.")
        return redirect("core:manage_users")
    return render(request, "manage/user_form.html", {"form": form, "managed_user": instance})


@require_POST
def user_deactivate_view(request, pk):
    _require_admin(request)
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        messages.success(request, f"{user.username} is now {'active' if user.is_active else 'deactivated'}.")
    return redirect("core:manage_users")


@require_POST
def user_invite_view(request, pk):
    _require_admin(request)
    user = get_object_or_404(User, pk=pk, is_active=True)
    try:
        send_account_setup_email(user, request)
    except Exception:
        messages.error(request, "Invitation delivery failed. Check the environment-based SMTP settings and try again.")
    else:
        messages.success(request, f"Sent a secure account-setup/reset link to {user.email}.")
    return redirect("core:manage_users")


def material_manage_list_view(request):
    _require_material_manager(request)
    materials = _material_queryset(request.user).annotate(chunk_total=Count("content_chunks"))
    course_id = request.GET.get("course", "")
    query = request.GET.get("q", "").strip()
    state = request.GET.get("state", "")
    if course_id.isdigit():
        materials = materials.filter(course_id=course_id)
    if query:
        materials = materials.filter(Q(title__icontains=query) | Q(authors__icontains=query))
    if state == "pending":
        materials = materials.filter(is_validated=False)
    elif state == "approved":
        materials = materials.filter(is_validated=True)
    elif state == "unindexed":
        materials = materials.filter(chunk_total=0)
    page = Paginator(materials.order_by("course__code", "-created_at"), 25).get_page(request.GET.get("page"))
    return render(
        request,
        "manage/material_list.html",
        {
            "page": page,
            "courses": _manageable_courses(request.user).order_by("code"),
            "filters": {"course": course_id, "q": query, "state": state},
        },
    )


def material_manage_edit_view(request, pk=None):
    _require_material_manager(request)
    courses = _manageable_courses(request.user)
    instance = get_object_or_404(_material_queryset(request.user), pk=pk) if pk else None
    old_course_id = instance.course_id if instance else None
    form = ManagedMaterialForm(
        request.POST or None, request.FILES or None, instance=instance, courses=courses, prefix="material"
    )
    if request.method == "POST" and form.is_valid():
        material = form.save(commit=False)
        if not instance:
            material.source_origin = Material.SourceOrigin.INTERNAL
            material.source_provider = f"Uploaded by {request.user.username}"
            material.source_endpoint = "management upload"
            material.source_record_id = material.source_record_id or f"manual-{material.title[:30]}"
            material.is_validated = True
            material.uploaded_by = request.user
        material.save()
        form.save_m2m()
        if material.file and (not instance or "file" in form.changed_data):
            try:
                chunks = index_material(material)
            except Exception as exc:
                messages.error(request, f"Saved {material.title}, but indexing failed: {exc}")
            else:
                if chunks:
                    messages.success(request, f"Saved {material.title} and indexed {len(chunks)} chunks.")
                else:
                    messages.warning(
                        request,
                        f"Saved {material.title}, but no text could be extracted, so the chatbot cannot use it. "
                        "Supported: PDF, DOCX, PPTX, TXT, MD, CSV, VTT, SRT (scanned PDFs and images are not).",
                    )
        else:
            if instance and old_course_id != material.course_id:
                for chunk in material.content_chunks.all():
                    chunk.metadata = {**chunk.metadata, "course_id": material.course_id}
                    chunk.save(update_fields=["metadata"])
                invalidate_retrieval_cache(old_course_id)
                invalidate_retrieval_cache(material.course_id)
            messages.success(request, f"Saved {material.title}.")
        return redirect("core:manage_materials")
    return render(request, "manage/material_form.html", {"form": form, "material": instance})


@require_POST
def material_manage_delete_view(request, pk):
    _require_material_manager(request)
    material = get_object_or_404(_material_queryset(request.user), pk=pk)
    title, course_id = material.title, material.course_id
    material.delete()
    invalidate_retrieval_cache(course_id)
    messages.success(request, f"Deleted {title} and all of its chunks.")
    return redirect("core:manage_materials")


@require_POST
def material_manage_reindex_view(request, pk):
    _require_material_manager(request)
    material = get_object_or_404(_material_queryset(request.user), pk=pk)
    try:
        chunks = index_material(material)
        if chunks:
            messages.success(request, f"Re-indexed {material.title}: {len(chunks)} chunks.")
        else:
            messages.warning(request, f"Re-indexed {material.title}, but no text could be extracted.")
    except Exception as exc:
        messages.error(request, f"Could not re-index {material.title}: {exc}")
    return redirect("core:manage_material_chunks", pk=material.pk)


def material_chunks_view(request, pk):
    _require_material_manager(request)
    material = get_object_or_404(_material_queryset(request.user), pk=pk)
    chunks = material.content_chunks.only(
        "id", "ordinal", "text", "page_number", "section_title", "token_count", "material_id"
    ).order_by("ordinal")
    page = Paginator(chunks, 25).get_page(request.GET.get("page"))
    return render(request, "manage/chunk_list.html", {"material": material, "page": page})


@require_POST
def chunks_delete_view(request, pk):
    _require_material_manager(request)
    material = get_object_or_404(_material_queryset(request.user), pk=pk)
    ids = [value for value in request.POST.getlist("chunk_ids") if value.isdigit()]
    if not ids:
        messages.error(request, "Select at least one chunk to delete.")
    else:
        deleted, _ = ContentChunk.objects.filter(material=material, pk__in=ids).delete()
        invalidate_retrieval_cache(material.course_id)
        messages.success(request, f"Deleted {deleted} chunk(s) from {material.title}.")
    return redirect("core:manage_material_chunks", pk=material.pk)
