from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
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
    return send_mail(
        subject=f"Set up your {institution_name} account",
        message=(
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"An administrator has granted you access to {institution_name}. "
            "Use the secure link below to set your password. If you were not expecting this invitation, "
            "you can ignore this email.\n\n"
            f"{setup_url}\n\n"
            "For your security, no password or SMTP credential is included in this message."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
