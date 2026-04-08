from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("new/", views.document_create, name="create"),
    # Hierarchical document routes — order matters: edit before detail
    # to avoid "edit" being treated as a child slug.
    path("<path:path>/edit/", views.document_edit, name="edit"),
    path("<path:path>/", views.document_detail, name="detail"),
]
