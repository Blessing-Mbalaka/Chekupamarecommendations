from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from learning.models import Material

@login_required
def protected_media(request, path):
    material = Material.objects.filter(file=path).first()
    if not material or (not material.is_validated and request.user.role not in {'admin', 'lecturer'} and not request.user.is_superuser):
        raise Http404('File not available.')
    try:
        return FileResponse(material.file.open('rb'))
    except (OSError, ValueError):
        raise Http404('File not available.')
