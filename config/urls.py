from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """Simple liveness probe — returns 200 OK so K8s knows the pod is up."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("", include("mcp_server.urls")),  # Registers /mcp/ endpoint
    path("search/", include("search.urls")),
    path("", include("documents.urls")),
]
