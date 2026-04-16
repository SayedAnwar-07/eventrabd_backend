from django.db import models
from django.utils.text import slugify
from bson.objectid import ObjectId
from django.utils import timezone


def generate_bson_id():
    return str(ObjectId())

class UIDMixin(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=24,
        default=generate_bson_id,
        editable=False,
        unique=True
    )

    class Meta:
        abstract = True

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

# Slug utility
def unique_slugify(instance, value, slug_field_name='slug'):
    from django.utils.text import slugify

    slug = slugify(value)
    ModelClass = instance.__class__
    qs = ModelClass.objects.exclude(id=instance.id)

    similar_slugs = qs.filter(**{f"{slug_field_name}__startswith": slug})

    if not similar_slugs.exists():
        final_slug = slug
    else:
        count = similar_slugs.count() + 1
        final_slug = f"{slug}-{count}"

    setattr(instance, slug_field_name, final_slug)