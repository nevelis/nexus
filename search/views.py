from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from documents.models import Document


@require_http_methods(["GET"])
def semantic_search(request):
    query = request.GET.get("q", "").strip()
    limit = min(int(request.GET.get("limit", 10)), 50)

    if not query:
        return JsonResponse({"results": [], "error": "query required"}, status=400)

    from .embeddings import generate_embedding

    embedding = generate_embedding(query)

    if embedding:
        # Vector similarity search
        from pgvector.django import CosineDistance

        docs = (
            Document.objects.filter(status="published", embedding__isnull=False)
            .annotate(distance=CosineDistance("embedding", embedding))
            .order_by("distance")[:limit]
        )
    else:
        # Fallback: keyword search
        docs = Document.objects.filter(status="published").filter(title__icontains=query)[:limit]

    results = [
        {
            "id": str(doc.id),
            "title": doc.title,
            "slug": doc.slug,
            "excerpt": doc.body[:200],
            "url": doc.get_absolute_url(),
            "score": float(1 - doc.distance) if embedding and hasattr(doc, "distance") else None,
        }
        for doc in docs
    ]

    return JsonResponse({"results": results, "query": query})
