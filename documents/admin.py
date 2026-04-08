from django.contrib import admin

from .models import Document, SlugAlias, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "parent", "status", "updated_at", "created_at"]
    list_filter = ["status", "tags", "parent"]
    search_fields = ["title", "body"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["id", "created_at", "updated_at"]
    filter_horizontal = ["tags"]
    raw_id_fields = ["parent"]


@admin.register(SlugAlias)
class SlugAliasAdmin(admin.ModelAdmin):
    list_display = ["slug", "document", "created_at"]
    search_fields = ["slug", "document__title"]
    raw_id_fields = ["document"]
