from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView

urlpatterns = [
    path("", include("organization.urls")),
    path("", include("prompts.urls")),
    path("", include("authentication.urls")),
    path("api/grade/", include("grade.urls")),
    path("api/", include("executor.urls")),
    path(
        "mini_ide",
        RedirectView.as_view(url="http://127.0.0.1:8001/mini_ide", permanent=False),
    ),
    path(
        "mini_ide/",
        RedirectView.as_view(url="http://127.0.0.1:8001/mini_ide", permanent=False),
    ),
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    # path('api/grade/', include('grade.urls')),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
