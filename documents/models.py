import uuid
from django.db import models
from django.utils.text import slugify
from pgvector.django import VectorField


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
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    body = models.TextField(help_text="Markdown content")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    tags = models.ManyToManyField(Tag, blank=True, related_name="documents")

    # Vector embedding — 384 dims for all-MiniLM-L6-v2 (sentence-transformers)
    embedding = VectorField(dimensions=384, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("documents:detail", kwargs={"slug": self.slug})
