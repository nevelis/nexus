"""Tests for the documents app: models, views, and MCP tools."""

from django.test import Client, TestCase

from .models import Document, Tag

# ── Tag model ────────────────────────────────────────────────────────────────


class TestTagModel(TestCase):
    def test_slug_auto_generated_from_name(self):
        tag = Tag.objects.create(name="Machine Learning")
        self.assertEqual(tag.slug, "machine-learning")

    def test_slug_preserved_when_provided(self):
        tag = Tag.objects.create(name="ML", slug="custom-slug")
        self.assertEqual(tag.slug, "custom-slug")

    def test_str_returns_name(self):
        tag = Tag(name="Python")
        self.assertEqual(str(tag), "Python")

    def test_ordering_is_alphabetical(self):
        Tag.objects.create(name="Zebra")
        Tag.objects.create(name="Apple")
        names = list(Tag.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Apple", "Zebra"])


# ── Document model ───────────────────────────────────────────────────────────


class TestDocumentModel(TestCase):
    def test_slug_auto_generated_from_title(self):
        doc = Document.objects.create(title="My First Post", body="content")
        self.assertEqual(doc.slug, "my-first-post")

    def test_slug_preserved_when_provided(self):
        doc = Document.objects.create(title="Post", slug="custom", body="content")
        self.assertEqual(doc.slug, "custom")

    def test_default_status_is_draft(self):
        doc = Document.objects.create(title="Doc", body="content")
        self.assertEqual(doc.status, Document.Status.DRAFT)

    def test_is_published_true_for_published(self):
        doc = Document(status=Document.Status.PUBLISHED)
        self.assertTrue(doc.is_published)

    def test_is_published_false_for_draft(self):
        doc = Document(status=Document.Status.DRAFT)
        self.assertFalse(doc.is_published)

    def test_is_published_false_for_archived(self):
        doc = Document(status=Document.Status.ARCHIVED)
        self.assertFalse(doc.is_published)

    def test_get_absolute_url(self):
        doc = Document.objects.create(title="Test", slug="test-slug", body="content")
        self.assertEqual(doc.get_absolute_url(), "/test-slug/")

    def test_str_returns_title(self):
        doc = Document(title="Hello World")
        self.assertEqual(str(doc), "Hello World")

    def test_uuid_primary_key(self):
        import uuid

        doc = Document.objects.create(title="Doc", body="content")
        self.assertIsInstance(doc.id, uuid.UUID)

    def test_ordering_most_recent_first(self):
        doc1 = Document.objects.create(title="First", body="content")
        Document.objects.create(title="Second", body="content")
        doc1.body = "updated"
        doc1.save()
        self.assertEqual(Document.objects.first(), doc1)


# ── Document list view ───────────────────────────────────────────────────────


class TestDocumentListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.published = Document.objects.create(
            title="Published Doc", body="body text", status="published"
        )
        self.draft = Document.objects.create(title="Draft Doc", body="body text", status="draft")
        self.archived = Document.objects.create(
            title="Archived Doc", body="body text", status="archived"
        )

    def test_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_defaults_to_published_status(self):
        response = self.client.get("/")
        docs = list(response.context["documents"])
        self.assertIn(self.published, docs)
        self.assertNotIn(self.draft, docs)
        self.assertNotIn(self.archived, docs)

    def test_filter_by_draft_status(self):
        response = self.client.get("/?status=draft")
        docs = list(response.context["documents"])
        self.assertIn(self.draft, docs)
        self.assertNotIn(self.published, docs)

    def test_filter_by_archived_status(self):
        response = self.client.get("/?status=archived")
        docs = list(response.context["documents"])
        self.assertIn(self.archived, docs)
        self.assertNotIn(self.published, docs)

    def test_htmx_request_returns_partial_template(self):
        response = self.client.get("/", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        template_names = [t.name for t in response.templates]
        self.assertIn("documents/partials/document_list.html", template_names)

    def test_keyword_search_filters_results(self):
        response = self.client.get("/?q=Published&status=published")
        docs = list(response.context["documents"])
        self.assertIn(self.published, docs)

    def test_tag_filter(self):
        tag = Tag.objects.create(name="python")
        self.published.tags.add(tag)
        response = self.client.get("/?tag=python&status=published")
        docs = list(response.context["documents"])
        self.assertIn(self.published, docs)

    def test_context_includes_tags(self):
        response = self.client.get("/")
        self.assertIn("tags", response.context)

    def test_context_includes_current_status(self):
        response = self.client.get("/?status=draft")
        self.assertEqual(response.context["current_status"], "draft")


# ── Document detail view ─────────────────────────────────────────────────────


class TestDocumentDetailView(TestCase):
    def setUp(self):
        self.client = Client()
        self.doc = Document.objects.create(
            title="Test Doc",
            slug="test-doc",
            body="# Heading\n\nSome **bold** text.",
        )

    def test_returns_200_for_existing_slug(self):
        response = self.client.get("/test-doc/")
        self.assertEqual(response.status_code, 200)

    def test_document_in_context(self):
        response = self.client.get("/test-doc/")
        self.assertEqual(response.context["document"], self.doc)

    def test_body_rendered_as_html(self):
        response = self.client.get("/test-doc/")
        # markdown 3.x adds id= attributes to headings: <h1 id="heading">…</h1>
        # Match the tag open without asserting the exact attribute list.
        self.assertIn("<h1", response.context["body_html"])
        self.assertIn("<strong>", response.context["body_html"])

    def test_returns_404_for_missing_slug(self):
        response = self.client.get("/this-does-not-exist/")
        self.assertEqual(response.status_code, 404)


# ── Document create view ─────────────────────────────────────────────────────


class TestDocumentCreateView(TestCase):
    def setUp(self):
        self.client = Client()

    def test_get_returns_200_with_form(self):
        response = self.client.get("/new/")
        self.assertEqual(response.status_code, 200)

    def test_post_creates_document_and_redirects(self):
        response = self.client.post(
            "/new/",
            {"title": "Brand New Doc", "body": "Some content", "status": "draft"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Document.objects.filter(title="Brand New Doc").exists())

    def test_post_without_title_returns_error(self):
        response = self.client.post("/new/", {"title": "", "body": "content"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)

    def test_post_with_tags_creates_tag_associations(self):
        self.client.post(
            "/new/",
            {"title": "Tagged Doc", "body": "content", "tags": "python, django"},
        )
        doc = Document.objects.get(title="Tagged Doc")
        tag_names = set(doc.tags.values_list("name", flat=True))
        self.assertEqual(tag_names, {"python", "django"})

    def test_post_redirects_to_document_detail(self):
        response = self.client.post(
            "/new/",
            {"title": "Redirect Test", "body": "body"},
            follow=False,
        )
        doc = Document.objects.get(title="Redirect Test")
        self.assertRedirects(response, doc.get_absolute_url(), fetch_redirect_response=False)


# ── Document edit view ───────────────────────────────────────────────────────


class TestDocumentEditView(TestCase):
    def setUp(self):
        self.client = Client()
        self.doc = Document.objects.create(
            title="Original Title",
            body="Original body",
            slug="original",
            status="draft",
        )

    def test_get_returns_200_with_document_in_context(self):
        response = self.client.get("/original/edit/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document"], self.doc)

    def test_get_includes_tag_string_in_context(self):
        tag = Tag.objects.create(name="mytag")
        self.doc.tags.add(tag)
        response = self.client.get("/original/edit/")
        self.assertIn("mytag", response.context["tag_str"])

    def test_post_updates_title_and_body(self):
        self.client.post(
            "/original/edit/",
            {"title": "Updated Title", "body": "Updated body", "status": "draft"},
        )
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, "Updated Title")
        self.assertEqual(self.doc.body, "Updated body")

    def test_post_updates_status(self):
        self.client.post(
            "/original/edit/",
            {"title": "Original Title", "body": "body", "status": "published"},
        )
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "published")

    def test_post_redirects(self):
        response = self.client.post(
            "/original/edit/",
            {"title": "Original Title", "body": "body", "status": "draft"},
        )
        self.assertEqual(response.status_code, 302)

    def test_post_replaces_tags(self):
        old_tag = Tag.objects.create(name="old-tag")
        self.doc.tags.add(old_tag)
        self.client.post(
            "/original/edit/",
            {"title": "Original Title", "body": "body", "status": "draft", "tags": "new-tag"},
        )
        tag_names = set(self.doc.tags.values_list("name", flat=True))
        self.assertEqual(tag_names, {"new-tag"})

    def test_htmx_post_returns_204_with_redirect_header(self):
        response = self.client.post(
            "/original/edit/",
            {"title": "HTMX Update", "body": "body", "status": "draft"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertIn("HX-Redirect", response)


# ── MCP: get_document ────────────────────────────────────────────────────────


class TestMCPGetDocument(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(
            title="MCP Doc",
            body="body content",
            slug="mcp-doc",
            status="published",
        )

    async def test_returns_document_data(self):
        from documents.mcp import get_document

        result = await get_document("mcp-doc")
        self.assertEqual(result["title"], "MCP Doc")
        self.assertEqual(result["body"], "body content")
        self.assertEqual(result["status"], "published")

    async def test_includes_required_fields(self):
        from documents.mcp import get_document

        result = await get_document("mcp-doc")
        for field in ("id", "title", "slug", "body", "status", "tags", "created_at", "updated_at"):
            self.assertIn(field, result)

    async def test_returns_error_for_missing_slug(self):
        from documents.mcp import get_document

        result = await get_document("no-such-slug")
        self.assertIn("error", result)

    async def test_includes_tags(self):
        from documents.mcp import get_document

        tag = await Tag.objects.acreate(name="mytag")
        await self.doc.tags.aadd(tag)
        result = await get_document("mcp-doc")
        self.assertIn("mytag", result["tags"])


# ── MCP: create_document ─────────────────────────────────────────────────────


class TestMCPCreateDocument(TestCase):
    async def test_creates_document_with_defaults(self):
        from documents.mcp import create_document

        result = await create_document(title="New Doc", body="some content")
        self.assertEqual(result["title"], "New Doc")
        self.assertEqual(result["status"], "draft")
        self.assertIn("id", result)
        self.assertIn("slug", result)

    async def test_creates_document_with_custom_status(self):
        from documents.mcp import create_document

        result = await create_document(title="Published", body="body", status="published")
        self.assertEqual(result["status"], "published")

    async def test_creates_document_with_tags(self):
        from documents.mcp import create_document

        result = await create_document(title="Tagged", body="body", tags=["python", "django"])
        self.assertEqual(set(result["tags"]), {"python", "django"})

    async def test_rejects_invalid_status(self):
        from documents.mcp import create_document

        result = await create_document(title="Bad", body="body", status="invalid")
        self.assertIn("error", result)

    async def test_document_persisted_to_db(self):
        from documents.mcp import create_document

        await create_document(title="Persisted", body="body")
        self.assertTrue(await Document.objects.filter(title="Persisted").aexists())


# ── MCP: update_document ─────────────────────────────────────────────────────


class TestMCPUpdateDocument(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(
            title="Original",
            body="original body",
            slug="update-me",
            status="draft",
        )

    async def test_updates_title(self):
        from documents.mcp import update_document

        result = await update_document("update-me", title="New Title")
        self.assertEqual(result["title"], "New Title")
        await self.doc.arefresh_from_db()
        self.assertEqual(self.doc.title, "New Title")

    async def test_updates_body(self):
        from documents.mcp import update_document

        await update_document("update-me", body="new body")
        await self.doc.arefresh_from_db()
        self.assertEqual(self.doc.body, "new body")

    async def test_updates_status(self):
        from documents.mcp import update_document

        result = await update_document("update-me", status="published")
        self.assertEqual(result["status"], "published")

    async def test_updates_tags(self):
        from documents.mcp import update_document

        result = await update_document("update-me", tags=["tag1", "tag2"])
        self.assertEqual(set(result["tags"]), {"tag1", "tag2"})

    async def test_clears_tags_with_empty_list(self):
        from documents.mcp import update_document

        tag = await Tag.objects.acreate(name="existing")
        await self.doc.tags.aadd(tag)
        result = await update_document("update-me", tags=[])
        self.assertEqual(result["tags"], [])

    async def test_returns_error_for_missing_document(self):
        from documents.mcp import update_document

        result = await update_document("does-not-exist")
        self.assertIn("error", result)

    async def test_returns_error_for_invalid_status(self):
        from documents.mcp import update_document

        result = await update_document("update-me", status="nonsense")
        self.assertIn("error", result)


# ── MCP: archive_document ────────────────────────────────────────────────────


class TestMCPArchiveDocument(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(
            title="To Archive",
            body="body",
            slug="archive-me",
            status="published",
        )

    async def test_sets_status_to_archived(self):
        from documents.mcp import archive_document

        result = await archive_document("archive-me")
        self.assertEqual(result["status"], "archived")
        await self.doc.arefresh_from_db()
        self.assertEqual(self.doc.status, "archived")

    async def test_returns_document_id_and_slug(self):
        from documents.mcp import archive_document

        result = await archive_document("archive-me")
        self.assertIn("id", result)
        self.assertEqual(result["slug"], "archive-me")

    async def test_returns_error_for_missing_document(self):
        from documents.mcp import archive_document

        result = await archive_document("no-such-slug")
        self.assertIn("error", result)


# ── MCP: list_documents ──────────────────────────────────────────────────────


class TestMCPListDocuments(TestCase):
    def setUp(self):
        Document.objects.create(title="Published", body="b", status="published")
        Document.objects.create(title="Draft", body="b", status="draft")
        Document.objects.create(title="Archived", body="b", status="archived")

    async def test_defaults_to_published(self):
        from documents.mcp import list_documents

        result = await list_documents()
        titles = [d["title"] for d in result]
        self.assertIn("Published", titles)
        self.assertNotIn("Draft", titles)

    async def test_filter_by_draft(self):
        from documents.mcp import list_documents

        result = await list_documents(status="draft")
        titles = [d["title"] for d in result]
        self.assertIn("Draft", titles)
        self.assertNotIn("Published", titles)

    async def test_status_all_returns_everything(self):
        from documents.mcp import list_documents

        result = await list_documents(status="all")
        self.assertEqual(len(result), 3)

    async def test_limit_is_respected(self):
        from documents.mcp import list_documents

        result = await list_documents(status="all", limit=2)
        self.assertEqual(len(result), 2)

    async def test_returns_error_for_invalid_status(self):
        from documents.mcp import list_documents

        result = await list_documents(status="bad-status")
        self.assertIn("error", result[0])

    async def test_result_includes_required_fields(self):
        from documents.mcp import list_documents

        result = await list_documents(status="all")
        for doc in result:
            for field in ("id", "title", "slug", "status", "tags", "updated_at"):
                self.assertIn(field, doc)


# ── MCP: search_documents ────────────────────────────────────────────────────


class TestMCPSearchDocuments(TestCase):
    """search_documents with generate_embedding mocked to None (keyword fallback via conftest)."""

    def setUp(self):
        Document.objects.create(
            title="Python Guide",
            body="Learn Python programming language",
            status="published",
        )
        Document.objects.create(
            title="Django Framework",
            body="Build web applications with Django",
            status="published",
        )
        Document.objects.create(
            title="Draft Python Doc",
            body="Python for drafts",
            status="draft",
        )

    async def test_keyword_search_finds_matching_docs(self):
        from documents.mcp import search_documents

        result = await search_documents("Python")
        titles = [d["title"] for d in result]
        self.assertIn("Python Guide", titles)

    async def test_keyword_search_filters_by_status(self):
        from documents.mcp import search_documents

        result = await search_documents("Python", status="published")
        titles = [d["title"] for d in result]
        self.assertNotIn("Draft Python Doc", titles)

    async def test_limit_is_respected(self):
        from documents.mcp import search_documents

        result = await search_documents("Python", limit=1)
        self.assertEqual(len(result), 1)

    async def test_limit_capped_at_50(self):
        from documents.mcp import search_documents

        result = await search_documents("Python", limit=100)
        self.assertLessEqual(len(result), 50)

    async def test_result_includes_required_fields(self):
        from documents.mcp import search_documents

        result = await search_documents("Python")
        for doc in result:
            for field in (
                "id",
                "title",
                "slug",
                "status",
                "excerpt",
                "score",
                "tags",
                "updated_at",
            ):
                self.assertIn(field, doc)

    async def test_keyword_fallback_score_is_none(self):
        from documents.mcp import search_documents

        result = await search_documents("Python")
        for doc in result:
            self.assertIsNone(doc["score"])
