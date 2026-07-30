import time
import random
import threading

from django.db import models
from django.utils.text import slugify
from django.utils import timezone


_counter = random.randint(0, 0xFFFFFF)
_counter_lock = threading.Lock()


def generate_bson_id():
    global _counter

    timestamp_hex = f"{int(time.time()):08x}"
    random_hex = f"{random.getrandbits(40):010x}"

    with _counter_lock:
        _counter = (_counter + 1) % 0xFFFFFF
        counter_hex = f"{_counter:06x}"

    return f"{timestamp_hex}{random_hex}{counter_hex}"


class UIDMixin(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=24,
        default=generate_bson_id,
        editable=False,
        unique=True,
    )

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def unique_slugify(instance, value, slug_field_name="slug"):
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