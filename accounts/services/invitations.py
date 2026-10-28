from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def account_setup_url(user, request) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    return request.build_absolute_uri(path)


def send_account_setup_email(user, request) -> int:
    """Send a signed setup/reset link. Passwords are never generated or emailed."""

    setup_url = account_setup_url(user, request)
    institution_name = getattr(getattr(user, "institution", None), "name", "the learning platform")
    modules = list(user.courses_taught.order_by("code").values("code", "title"))
    module_names = ", ".join(module["code"] for module in modules)
    module_line = f"Approved teaching modules: {module_names}.\n\n" if module_names else ""
    html_message = render_to_string("emails/account_activation.html", {
        "recipient_name": user.get_full_name() or user.username,
        "institution_name": institution_name,
        "modules": modules,
        "setup_url": setup_url,
    })
    return send_mail(
        subject=f"Your {institution_name} account is active",
        message=(
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"An administrator has activated your access to {institution_name}.\n\n"
            f"{module_line}"
            "Use the secure link below to set your password. If you were not expecting this invitation, "
            "you can ignore this email.\n\n"
            f"{setup_url}\n\n"
            "For your security, no password or SMTP credential is included in this message."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
        html_message=html_message,
    )


def send_module_allocation_email(user, request) -> int:
    institution_name = getattr(getattr(user, "institution", None), "name", "the learning platform")
    modules = list(user.courses_taught.order_by("code").values_list("code", "title"))
    module_lines = "\n".join(f"- {code}: {title}" for code, title in modules) or "- No modules currently allocated"
    sign_in_url = request.build_absolute_uri(reverse("login"))
    html_message = render_to_string("emails/module_allocation.html", {
        "recipient_name": user.get_full_name() or user.username,
        "institution_name": institution_name,
        "modules": modules,
        "sign_in_url": sign_in_url,
    })
    return send_mail(
        subject=f"Your {institution_name} module allocation was updated",
        message=(
            f"Hello {user.get_full_name() or user.username},\n\n"
            "An administrator updated the modules allocated to your lecturer account:\n\n"
            f"{module_lines}\n\n"
            "Sign in to view and manage only the materials assigned to your account."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
        html_message=html_message,
    )
