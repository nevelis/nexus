from django.contrib import admin

from .models import Document, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "updated_at", "created_at"]
    list_filter = ["status", "tags"]
    search_fields = ["title", "body"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["id", "created_at", "updated_at"]
    filter_horizontal = ["tags"]
