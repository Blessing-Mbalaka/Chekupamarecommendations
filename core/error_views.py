from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

LOGIN_PATHS = {"/login/", "/curation/login/"}


def _render(request, status, title, message):
    return render(
        request,
        "errors/error.html",
        {"status": status, "title": title, "message": message},
        status=status,
    )


def csrf_failure(request, reason=""):
    # A stale token usually means the login page was open in another tab or
    # browser session; a fresh GET issues a new token, so send the user back.
    if request.path in LOGIN_PATHS:
        messages.info(request, "Your sign-in page had expired. Please sign in again.")
        return redirect(request.path)
    return _render(
        request,
        403,
        "Session expired",
        "Your session or form expired. Go back, refresh the page and try again.",
    )


def bad_request(request, exception=None):
    return _render(request, 400, "Bad request", "We could not understand that request.")


def permission_denied(request, exception=None):
    return _render(request, 403, "Access denied", "You do not have permission to view this page.")


def page_not_found(request, exception=None):
    return _render(request, 404, "Page not found", "The page you are looking for does not exist or has moved.")


def server_error(request):
    return _render(request, 500, "Something went wrong", "An unexpected error occurred. Please try again shortly.")
