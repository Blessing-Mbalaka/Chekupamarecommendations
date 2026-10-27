"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from institutions.media import protected_media

from accounts.views import DemoLoginView, superuser_login_view

handler400 = 'core.error_views.bad_request'
handler403 = 'core.error_views.permission_denied'
handler404 = 'core.error_views.page_not_found'
handler500 = 'core.error_views.server_error'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('institutions/', include('institutions.urls')),
    path('learning/', include('learning.urls')),
    path('chatbot/', include('chatbot.urls')),
    path('analytics/', include('analytics_app.urls')),
    path(
        'login/',
        DemoLoginView.as_view(),
        name='login',
    ),
    path('curation/login/', superuser_login_view, name='superuser_login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path(
        'accounts/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path(
        'accounts/reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
]

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', protected_media),
]
