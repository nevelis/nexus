from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("new/", views.document_create, name="create"),
    path("<slug:slug>/", views.document_detail, name="detail"),
    path("<slug:slug>/edit/", views.document_edit, name="edit"),
]
