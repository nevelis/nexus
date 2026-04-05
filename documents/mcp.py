"""
MCP tools for Nexus document operations.

Autodiscovered by django-mcp-server when it starts up.
Tools are registered on the global MCP server and exposed at /mcp/.
"""
from mcp_server import mcp_server as mcp
from .models import Document, Tag


@mcp.tool()
def search_documents(query: str, limit: int = 10, status: str = "published") -> list[dict]:
    """Search documents by semantic similarity (when embeddings available) or keyword.

    Args:
        query: Search query text
        limit: Max results to return (default 10, max 50)
        status: Filter by status — 'published', 'draft', or 'archived'

    Returns:
        List of matching documents with id, title, slug, excerpt, url
    """
    limit = min(limit, 50)
    qs = Document.objects.filter(status=status)

    from search.embeddings import generate_embedding
    embedding = generate_embedding(query)

    if embedding:
        from pgvector.django import CosineDistance
        docs = (
            qs.filter(embedding__isnull=False)
            .annotate(distance=CosineDistance("embedding", embedding))
            .order_by("distance")[:limit]
        )
        results = []
        for doc in docs:
            results.append({
                "id": str(doc.id),
                "title": doc.title,
                "slug": doc.slug,
                "status": doc.status,
                "excerpt": doc.body[:300],
                "score": round(float(1 - doc.distance), 4),
                "tags": list(doc.tags.values_list("name", flat=True)),
                "updated_at": doc.updated_at.isoformat(),
            })
        return results
    else:
        # Keyword fallback
        docs = (
            qs.filter(title__icontains=query) | qs.filter(body__icontains=query)
        ).distinct()[:limit]
        return [
            {
                "id": str(doc.id),
                "title": doc.title,
                "slug": doc.slug,
                "status": doc.status,
                "excerpt": doc.body[:300],
                "score": None,
                "tags": list(doc.tags.values_list("name", flat=True)),
                "updated_at": doc.updated_at.isoformat(),
            }
            for doc in docs
        ]


@mcp.tool()
def get_document(slug: str) -> dict:
    """Get a document by its slug.

    Args:
        slug: The document's URL slug

    Returns:
        Full document data including body (markdown), tags, status, timestamps
    """
    try:
        doc = Document.objects.get(slug=slug)
    except Document.DoesNotExist:
        return {"error": f"Document '{slug}' not found"}

    return {
        "id": str(doc.id),
        "title": doc.title,
        "slug": doc.slug,
        "body": doc.body,
        "status": doc.status,
        "tags": list(doc.tags.values_list("name", flat=True)),
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


@mcp.tool()
def create_document(
    title: str,
    body: str,
    status: str = "draft",
    tags: list[str] | None = None,
) -> dict:
    """Create a new document.

    Args:
        title: Document title
        body: Document content in Markdown
        status: 'draft' (default), 'published', or 'archived'
        tags: Optional list of tag names

    Returns:
        Created document data including id and slug
    """
    if status not in Document.Status.values:
        return {"error": f"Invalid status '{status}'. Choose: {Document.Status.values}"}

    doc = Document.objects.create(title=title, body=body, status=status)

    if tags:
        for name in tags:
            tag, _ = Tag.objects.get_or_create(name=name.strip())
            doc.tags.add(tag)

    # Generate embedding inline
    try:
        from search.embeddings import generate_embedding
        embedding = generate_embedding(f"{doc.title}\n\n{doc.body}")
        if embedding:
            doc.embedding = embedding
            doc.save(update_fields=["embedding"])
    except Exception:
        pass

    return {
        "id": str(doc.id),
        "title": doc.title,
        "slug": doc.slug,
        "status": doc.status,
        "tags": list(doc.tags.values_list("name", flat=True)),
        "created_at": doc.created_at.isoformat(),
    }


@mcp.tool()
def update_document(
    slug: str,
    title: str | None = None,
    body: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Update an existing document.

    Args:
        slug: The document's URL slug
        title: New title (optional)
        body: New markdown body (optional)
        status: New status (optional)
        tags: Replace tags list (optional — pass empty list to clear)

    Returns:
        Updated document data
    """
    try:
        doc = Document.objects.get(slug=slug)
    except Document.DoesNotExist:
        return {"error": f"Document '{slug}' not found"}

    if title is not None:
        doc.title = title
    if body is not None:
        doc.body = body
    if status is not None:
        if status not in Document.Status.values:
            return {"error": f"Invalid status '{status}'"}
        doc.status = status

    doc.save()

    if tags is not None:
        doc.tags.clear()
        for name in tags:
            tag, _ = Tag.objects.get_or_create(name=name.strip())
            doc.tags.add(tag)

    # Regenerate embedding if content changed
    if title is not None or body is not None:
        try:
            from search.embeddings import generate_embedding
            embedding = generate_embedding(f"{doc.title}\n\n{doc.body}")
            if embedding:
                doc.embedding = embedding
                doc.save(update_fields=["embedding"])
        except Exception:
            pass

    return {
        "id": str(doc.id),
        "title": doc.title,
        "slug": doc.slug,
        "status": doc.status,
        "tags": list(doc.tags.values_list("name", flat=True)),
        "updated_at": doc.updated_at.isoformat(),
    }


@mcp.tool()
def archive_document(slug: str) -> dict:
    """Archive a document (soft delete — sets status to 'archived').

    Args:
        slug: The document's URL slug

    Returns:
        Confirmation with document id and slug
    """
    try:
        doc = Document.objects.get(slug=slug)
    except Document.DoesNotExist:
        return {"error": f"Document '{slug}' not found"}

    doc.status = Document.Status.ARCHIVED
    doc.save(update_fields=["status", "updated_at"])

    return {
        "id": str(doc.id),
        "slug": doc.slug,
        "status": doc.status,
        "message": f"Document '{doc.title}' archived.",
    }


@mcp.tool()
def list_documents(status: str = "published", limit: int = 20) -> list[dict]:
    """List documents, optionally filtered by status.

    Args:
        status: Filter by status — 'published' (default), 'draft', 'archived', or 'all'
        limit: Max results (default 20, max 100)

    Returns:
        List of documents ordered by most recently updated
    """
    limit = min(limit, 100)
    qs = Document.objects.all()

    if status != "all":
        if status not in Document.Status.values:
            return [{"error": f"Invalid status '{status}'"}]
        qs = qs.filter(status=status)

    return [
        {
            "id": str(doc.id),
            "title": doc.title,
            "slug": doc.slug,
            "status": doc.status,
            "tags": list(doc.tags.values_list("name", flat=True)),
            "updated_at": doc.updated_at.isoformat(),
        }
        for doc in qs[:limit]
    ]
