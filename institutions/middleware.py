from django.http import HttpResponseForbidden
from .tenancy import institution_context

class InstitutionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)
        institution = request.user.institution
        if not institution.is_active:
            from django.contrib.auth import logout
            logout(request)
            return HttpResponseForbidden('This institution is inactive. Please sign in with an active account.')
        request.institution = institution
        with institution_context(institution, request.user):
            response = self.get_response(request)
            if hasattr(response, 'render') and not response.is_rendered:
                response.render()
            if response.streaming:
                original = response.streaming_content
                def stream():
                    with institution_context(institution, request.user):
                        yield from original
                response.streaming_content = stream()
            response['Cache-Control'] = 'private, no-store'
            return response
