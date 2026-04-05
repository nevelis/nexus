import markdown as md
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from .models import Document, Tag


def document_list(request):
    status = request.GET.get("status", "published")
    tag_slug = request.GET.get("tag")
    query = request.GET.get("q", "").strip()

    docs = Document.objects.all()

    if status in Document.Status.values:
        docs = docs.filter(status=status)

    if tag_slug:
        docs = docs.filter(tags__slug=tag_slug)

    if query:
        docs = docs.filter(title__icontains=query) | docs.filter(body__icontains=query)

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


def document_detail(request, slug):
    doc = get_object_or_404(Document, slug=slug)
    body_html = md.markdown(
        doc.body,
        extensions=["fenced_code", "tables", "toc", "nl2br"],
    )
    context = {"document": doc, "body_html": body_html}
    return render(request, "documents/detail.html", context)


@require_http_methods(["GET", "POST"])
def document_create(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        status = request.POST.get("status", Document.Status.DRAFT)
        tag_names = [t.strip() for t in request.POST.get("tags", "").split(",") if t.strip()]

        if not title:
            return render(request, "documents/create.html", {"error": "Title is required."})

        doc = Document.objects.create(title=title, body=body, status=status)

        for name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=name, defaults={"name": name})
            doc.tags.add(tag)

        # Kick off embedding generation asynchronously (stubbed for now)
        _schedule_embedding(doc)

        return redirect(doc.get_absolute_url())

    return render(request, "documents/create.html", {"statuses": Document.Status.choices})


@require_http_methods(["GET", "POST"])
def document_edit(request, slug):
    doc = get_object_or_404(Document, slug=slug)

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
