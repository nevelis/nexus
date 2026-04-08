import markdown as md
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import Document, SlugAlias, Tag


def _resolve_document_by_path(path):
    """Resolve a hierarchical path like 'pit/strategy' to a Document.

    Walks the path segments from root to leaf, following parent-child
    relationships.  The final segment is fetched with ``select_related``
    for the parent chain so that ``get_path()`` / ``get_absolute_url()``
    don't trigger extra queries.

    Returns the Document or raises Http404.
    Falls back to SlugAlias lookup for old flat URLs (returns redirect).
    """
    segments = [s for s in path.strip("/").split("/") if s]
    if not segments:
        raise Http404("Empty path")

    # Walk the hierarchy: first segment is a root doc, rest are children.
    # Use select_related on the last segment so the parent chain is cached.
    doc = None
    parent = None
    for i, segment in enumerate(segments):
        try:
            qs = Document.objects.all()
            # Eager-load parent chain on the final segment
            if i == len(segments) - 1:
                qs = qs.select_related("parent__parent__parent")
            doc = qs.get(slug=segment, parent=parent)
        except Document.DoesNotExist:
            doc = None
            break
        parent = doc

    if doc is not None:
        return doc

    # Fallback: try slug alias (for old flat URLs)
    # Only try if the path is a single segment (flat slug)
    if len(segments) == 1:
        try:
            alias = SlugAlias.objects.select_related(
                "document__parent__parent__parent",
            ).get(slug=segments[0])
            return alias  # Caller checks isinstance to decide redirect vs render
        except SlugAlias.DoesNotExist:
            pass

    raise Http404(f"Document not found at path: {path}")


def document_list(request):
    status = request.GET.get("status", "published")
    tag_slug = request.GET.get("tag")
    query = request.GET.get("q", "").strip()

    docs = Document.objects.select_related("parent__parent__parent").prefetch_related("tags").all()

    if status in Document.Status.values:
        docs = docs.filter(status=status)

    if tag_slug:
        docs = docs.filter(tags__slug=tag_slug)

    # Use Q objects for a single query instead of queryset OR (which can duplicate rows)
    if query:
        docs = docs.filter(Q(title__icontains=query) | Q(body__icontains=query))

    tags = Tag.objects.all()

    context = {
        "documents": docs.distinct(),
        "tags": tags,
        "current_status": status,
        "current_tag": tag_slug,
        "query": query,
    }

    if request.headers.get("HX-Request"):
        return render(request, "documents/partials/document_list.html", context)
    return render(request, "documents/list.html", context)


def document_detail(request, path):
    result = _resolve_document_by_path(path)

    # SlugAlias → 301 redirect to canonical hierarchical URL
    if isinstance(result, SlugAlias):
        return redirect(result.document.get_absolute_url(), permanent=True)

    doc = result
    body_html = md.markdown(
        doc.body,
        extensions=["fenced_code", "tables", "toc", "nl2br"],
    )

    # Build breadcrumbs from ancestry (parent chain already eager-loaded
    # by _resolve_document_by_path via select_related)
    ancestors = doc.get_ancestors()
    breadcrumbs = [{"title": a.title, "url": a.get_absolute_url()} for a in ancestors]

    # Prefetch tags for the detail doc in a single query
    from django.db.models import prefetch_related_objects

    prefetch_related_objects([doc], "tags")

    # Children of this document — eager-load parent chain so
    # child.get_absolute_url() doesn't trigger extra queries
    children = (
        doc.children.select_related("parent__parent__parent")
        .filter(status=Document.Status.PUBLISHED)
        .order_by("title")
    )

    context = {
        "document": doc,
        "body_html": body_html,
        "breadcrumbs": breadcrumbs,
        "children": children,
    }
    return render(request, "documents/detail.html", context)


@require_http_methods(["GET", "POST"])
def document_create(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        status = request.POST.get("status", Document.Status.DRAFT)
        tag_names = [t.strip() for t in request.POST.get("tags", "").split(",") if t.strip()]
        parent_slug = request.POST.get("parent", "").strip()

        if not title:
            return render(request, "documents/create.html", {"error": "Title is required."})

        parent = None
        if parent_slug:
            parent = get_object_or_404(Document, slug=parent_slug, parent__isnull=True)

        doc = Document.objects.create(title=title, body=body, status=status, parent=parent)

        for name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=name, defaults={"name": name})
            doc.tags.add(tag)

        # Kick off embedding generation asynchronously (stubbed for now)
        _schedule_embedding(doc)

        return redirect(doc.get_absolute_url())

    return render(request, "documents/create.html", {"statuses": Document.Status.choices})


@require_http_methods(["GET", "POST"])
def document_edit(request, path):
    result = _resolve_document_by_path(path)
    if isinstance(result, SlugAlias):
        return redirect(result.document.get_absolute_url() + "edit/", permanent=True)

    doc = result

    if request.method == "POST":
        doc.title = request.POST.get("title", doc.title).strip()
        doc.body = request.POST.get("body", doc.body).strip()
        doc.status = request.POST.get("status", doc.status)
        doc.save()

        tag_names = [t.strip() for t in request.POST.get("tags", "").split(",") if t.strip()]
        doc.tags.clear()
        for name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=name, defaults={"name": name})
            doc.tags.add(tag)

        _schedule_embedding(doc)

        if request.headers.get("HX-Request"):
            from django.http import HttpResponse

            response = HttpResponse(status=204)
            response["HX-Redirect"] = doc.get_absolute_url()
            return response

        return redirect(doc.get_absolute_url())

    tag_str = ", ".join(doc.tags.values_list("name", flat=True))
    context = {
        "document": doc,
        "tag_str": tag_str,
        "statuses": Document.Status.choices,
    }
    return render(request, "documents/edit.html", context)


def _schedule_embedding(doc):
    """Queue an embedding update. Runs inline for now; swap for Celery task later."""
    try:
        from search.embeddings import generate_embedding

        embedding = generate_embedding(f"{doc.title}\n\n{doc.body}")
        doc.embedding = embedding
        doc.save(update_fields=["embedding"])
    except Exception:
        pass  # Don't block on embedding failures
