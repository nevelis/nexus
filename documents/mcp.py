"""
MCP tools for Nexus document operations.

Autodiscovered by django-mcp-server when it starts up.
Tools are registered on the global MCP server and exposed at /mcp/.

Note: All tool functions must be async and wrap ORM calls with
sync_to_async, because FastMCP's @mcp.tool() runs handlers in an
async context without automatic sync wrapping (unlike MCPToolset).
"""

from asgiref.sync import sync_to_async
from mcp_server import mcp_server as mcp

from .models import Document, Tag


def _doc_to_dict(doc, include_body=False):
    """Serialize a Document to a dict with hierarchy info."""
    data = {
        "id": str(doc.id),
        "title": doc.title,
        "slug": doc.slug,
        "path": doc.get_path(),
        "url": doc.get_absolute_url(),
        "status": doc.status,
        "parent_slug": doc.parent.slug if doc.parent else None,
        "tags": list(doc.tags.values_list("name", flat=True)),
        "updated_at": doc.updated_at.isoformat(),
    }
    if include_body:
        data["body"] = doc.body
        data["created_at"] = doc.created_at.isoformat()
    return data


@mcp.tool()
async def search_documents(query: str, limit: int = 10, status: str = "published") -> list[dict]:
    """Search documents by semantic similarity (when embeddings available) or keyword.

    Args:
        query: Search query text
        limit: Max results to return (default 10, max 50)
        status: Filter by status — 'published', 'draft', or 'archived'

    Returns:
        List of matching documents with id, title, slug, path, excerpt, url
    """

    def _search():
        _limit = min(limit, 50)
        qs = Document.objects.select_related("parent__parent__parent").filter(status=status)

        from search.embeddings import generate_embedding

        embedding = generate_embedding(query)

        if embedding is not None:
            from pgvector.django import CosineDistance

            docs = (
                qs.filter(embedding__isnull=False)
                .annotate(distance=CosineDistance("embedding", embedding))
                .order_by("distance")[:_limit]
            )
            results = []
            for doc in docs:
                results.append(
                    {
                        "id": str(doc.id),
                        "title": doc.title,
                        "slug": doc.slug,
                        "path": doc.get_path(),
                        "url": doc.get_absolute_url(),
                        "status": doc.status,
                        "excerpt": doc.body[:300],
                        "score": round(float(1 - doc.distance), 4),
                        "tags": list(doc.tags.values_list("name", flat=True)),
                        "updated_at": doc.updated_at.isoformat(),
                    }
                )
            return results
        else:
            # Keyword fallback
            docs = (
                qs.filter(title__icontains=query) | qs.filter(body__icontains=query)
            ).distinct()[:_limit]
            return [
                {
                    "id": str(doc.id),
                    "title": doc.title,
                    "slug": doc.slug,
                    "path": doc.get_path(),
                    "url": doc.get_absolute_url(),
                    "status": doc.status,
                    "excerpt": doc.body[:300],
                    "score": None,
                    "tags": list(doc.tags.values_list("name", flat=True)),
                    "updated_at": doc.updated_at.isoformat(),
                }
                for doc in docs
            ]

    return await sync_to_async(_search, thread_sensitive=False)()


@mcp.tool()
async def get_document(slug: str) -> dict:
    """Get a document by its slug or hierarchical path.

    Args:
        slug: The document's URL slug or path (e.g. 'pit' or 'pit/strategy')

    Returns:
        Full document data including body (markdown), tags, status, timestamps, path
    """

    def _get():
        # Try hierarchical path resolution
        segments = [s for s in slug.strip("/").split("/") if s]
        doc = None
        parent = None
        for segment in segments:
            try:
                doc = Document.objects.get(slug=segment, parent=parent)
            except Document.DoesNotExist:
                return {"error": f"Document '{slug}' not found"}
            parent = doc

        if doc is None:
            return {"error": f"Document '{slug}' not found"}

        return _doc_to_dict(doc, include_body=True)

    return await sync_to_async(_get, thread_sensitive=False)()


@mcp.tool()
async def create_document(
    title: str,
    body: str,
    status: str = "draft",
    tags: list[str] | None = None,
    parent_slug: str | None = None,
) -> dict:
    """Create a new document.

    Args:
        title: Document title
        body: Document content in Markdown
        status: 'draft' (default), 'published', or 'archived'
        tags: Optional list of tag names
        parent_slug: Optional parent document slug (for nesting)

    Returns:
        Created document data including id, slug, and path
    """

    def _create():
        if status not in Document.Status.values:
            return {"error": f"Invalid status '{status}'. Choose: {Document.Status.values}"}

        parent = None
        if parent_slug:
            try:
                parent = Document.objects.get(slug=parent_slug)
            except Document.DoesNotExist:
                return {"error": f"Parent document '{parent_slug}' not found"}

        doc = Document.objects.create(title=title, body=body, status=status, parent=parent)

        if tags:
            for name in tags:
                tag, _ = Tag.objects.get_or_create(name=name.strip())
                doc.tags.add(tag)

        # Generate embedding inline
        try:
            from search.embeddings import generate_embedding

            embedding = generate_embedding(f"{doc.title}\n\n{doc.body}")
            if embedding is not None:
                doc.embedding = embedding
                doc.save(update_fields=["embedding"])
        except Exception:
            pass

        return _doc_to_dict(doc, include_body=False)

    return await sync_to_async(_create, thread_sensitive=False)()


@mcp.tool()
async def update_document(
    slug: str,
    title: str | None = None,
    body: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Update an existing document.

    Args:
        slug: The document's URL slug or path
        title: New title (optional)
        body: New markdown body (optional)
        status: New status (optional)
        tags: Replace tags list (optional — pass empty list to clear)

    Returns:
        Updated document data
    """

    def _update():
        # Resolve by path
        segments = [s for s in slug.strip("/").split("/") if s]
        doc = None
        parent = None
        for segment in segments:
            try:
                doc = Document.objects.get(slug=segment, parent=parent)
            except Document.DoesNotExist:
                return {"error": f"Document '{slug}' not found"}
            parent = doc

        if doc is None:
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
                if embedding is not None:
                    doc.embedding = embedding
                    doc.save(update_fields=["embedding"])
            except Exception:
                pass

        return _doc_to_dict(doc)

    return await sync_to_async(_update, thread_sensitive=False)()


@mcp.tool()
async def archive_document(slug: str) -> dict:
    """Archive a document (soft delete — sets status to 'archived').

    Args:
        slug: The document's URL slug or path

    Returns:
        Confirmation with document id and slug
    """

    def _archive():
        # Resolve by path
        segments = [s for s in slug.strip("/").split("/") if s]
        doc = None
        parent = None
        for segment in segments:
            try:
                doc = Document.objects.get(slug=segment, parent=parent)
            except Document.DoesNotExist:
                return {"error": f"Document '{slug}' not found"}
            parent = doc

        if doc is None:
            return {"error": f"Document '{slug}' not found"}

        doc.status = Document.Status.ARCHIVED
        doc.save(update_fields=["status", "updated_at"])

        return {
            "id": str(doc.id),
            "slug": doc.slug,
            "path": doc.get_path(),
            "status": doc.status,
            "message": f"Document '{doc.title}' archived.",
        }

    return await sync_to_async(_archive, thread_sensitive=False)()


@mcp.tool()
async def list_documents(status: str = "published", limit: int = 20) -> list[dict]:
    """List documents, optionally filtered by status.

    Args:
        status: Filter by status — 'published' (default), 'draft', 'archived', or 'all'
        limit: Max results (default 20, max 100)

    Returns:
        List of documents ordered by most recently updated
    """

    def _list():
        _limit = min(limit, 100)
        qs = Document.objects.select_related("parent__parent__parent").all()

        if status != "all":
            if status not in Document.Status.values:
                return [{"error": f"Invalid status '{status}'"}]
            qs = qs.filter(status=status)

        return [_doc_to_dict(doc) for doc in qs[:_limit]]

    return await sync_to_async(_list, thread_sensitive=False)()
