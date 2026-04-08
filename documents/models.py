import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from pgvector.django import VectorField

# Maximum nesting depth: root (1) → child (2) → grandchild (3)
MAX_DEPTH = 3


class Tag(models.Model):
    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=64, unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class Document(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    body = models.TextField(help_text="Markdown content")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    tags = models.ManyToManyField(Tag, blank=True, related_name="documents")

    # Parent-child hierarchy (nullable — root docs have no parent)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )

    # Vector embedding — 384 dims for all-MiniLM-L6-v2 (remote embeddings API)
    embedding = VectorField(dimensions=384, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        # Slug must be unique among siblings (same parent)
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "slug"],
                name="unique_slug_per_parent",
            ),
            # Root-level docs (parent=NULL) must have unique slugs
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(parent__isnull=True),
                name="unique_root_slug",
            ),
        ]

    def clean(self):
        """Validate depth cap and prevent circular references."""
        super().clean()
        if self.parent:
            # Check for circular reference
            ancestor = self.parent
            seen = set()
            while ancestor is not None:
                if ancestor.pk == self.pk:
                    raise ValidationError(
                        "A document cannot be its own ancestor (circular reference)."
                    )
                if ancestor.pk in seen:
                    break  # Safety: avoid infinite loop on corrupted data
                seen.add(ancestor.pk)
                ancestor = ancestor.parent

            # Check depth cap
            depth = self._get_depth()
            if depth > MAX_DEPTH:
                raise ValidationError(
                    f"Maximum nesting depth is {MAX_DEPTH} levels. This would create depth {depth}."
                )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        # Run validation unless explicitly skipped (e.g. update_fields)
        if not kwargs.get("update_fields"):
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    def _get_depth(self):
        """Return the 1-based depth of this document in the hierarchy."""
        depth = 1
        ancestor = self.parent
        while ancestor is not None:
            depth += 1
            ancestor = ancestor.parent
        return depth

    def get_ancestors(self):
        """Return list of ancestors from root to immediate parent."""
        ancestors = []
        ancestor = self.parent
        while ancestor is not None:
            ancestors.append(ancestor)
            ancestor = ancestor.parent
        ancestors.reverse()
        return ancestors

    def get_path(self):
        """Return the full hierarchical path (e.g. 'pit/strategy')."""
        parts = [a.slug for a in self.get_ancestors()] + [self.slug]
        return "/".join(parts)

    def get_absolute_url(self):
        return f"/{self.get_path()}/"


class SlugAlias(models.Model):
    """Maps old flat slugs to documents for 301 redirects.

    When a document is moved into a hierarchy, its old flat URL
    (e.g. /pit-strategy/) gets an alias pointing to the new
    hierarchical URL (e.g. /pit/strategy/).
    """

    slug = models.SlugField(max_length=255, unique=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="aliases")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "slug aliases"

    def __str__(self):
        return f"{self.slug} → {self.document.get_path()}"
