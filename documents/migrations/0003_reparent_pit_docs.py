"""Reparent pit-* documents under the 'pit' parent and create slug aliases.

Task-201 added nested page support. This migration moves all pit-related
documents from the root level into the 'pit' hierarchy and creates
SlugAlias records so old flat URLs (e.g. /pit-strategy/) 301-redirect
to the new hierarchical URLs (e.g. /pit/strategy/).
"""

from django.db import migrations

# Old slug -> new (short) slug under pit parent
PIT_CHILDREN = {
    "pit-strategy": "strategy",
    "pit-day-1-simulation": "day-1-simulation",
    "pit-acronyms-glossary": "acronyms-glossary",
    "pit-futures-for-dummies": "futures-for-dummies",
    "pit-day-2-tuesday-april-7-2026": "day-2-tuesday-april-7-2026",
    "pit-agent-roles-workflow": "agent-roles-workflow",
    "pit-pm-simulation-day-1-april-7-2026": "pm-simulation-day-1-april-7-2026",
    "pit-prediction-markets-strategy": "prediction-markets-strategy",
    "pit-brand-brief-voice-tone-positioning-guide": "brand-brief-voice-tone-positioning-guide",
    "pit-landing-page-copy-draft-v1": "landing-page-copy-draft-v1",
    "pit-multi-agent-trading-signal-platform": "multi-agent-trading-signal-platform",
}


def reparent_pit_docs(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    SlugAlias = apps.get_model("documents", "SlugAlias")

    try:
        pit = Document.objects.get(slug="pit", parent__isnull=True)
    except Document.DoesNotExist:
        # Nothing to do if the pit doc doesn't exist yet
        return

    for old_slug, new_slug in PIT_CHILDREN.items():
        try:
            doc = Document.objects.get(slug=old_slug, parent__isnull=True)
        except Document.DoesNotExist:
            continue  # Skip docs that don't exist

        # Reparent and shorten slug
        doc.parent = pit
        doc.slug = new_slug
        doc.save(update_fields=["parent", "slug"])

        # Create redirect alias from old flat slug
        SlugAlias.objects.get_or_create(
            slug=old_slug,
            defaults={"document": doc},
        )


def unreparent_pit_docs(apps, schema_editor):
    """Reverse: move docs back to root with original flat slugs."""
    Document = apps.get_model("documents", "Document")
    SlugAlias = apps.get_model("documents", "SlugAlias")

    for old_slug, new_slug in PIT_CHILDREN.items():
        try:
            pit = Document.objects.get(slug="pit", parent__isnull=True)
            doc = Document.objects.get(slug=new_slug, parent=pit)
        except Document.DoesNotExist:
            continue

        doc.parent = None
        doc.slug = old_slug
        doc.save(update_fields=["parent", "slug"])

        # Remove the alias
        SlugAlias.objects.filter(slug=old_slug).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_add_hierarchy_and_aliases"),
    ]

    operations = [
        migrations.RunPython(reparent_pit_docs, unreparent_pit_docs),
    ]
