from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("mcp_server.urls")),   # Registers /mcp/ endpoint
    path("search/", include("search.urls")),
    path("", include("documents.urls")),
]
