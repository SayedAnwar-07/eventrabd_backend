from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db.models import UniqueConstraint
from apps.users.models import User
from django.utils.crypto import get_random_string
from datetime import timedelta


def generate_unique_id():
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    while True:
        new_id = get_random_string(8, allowed_chars=alphabet)
        if not Event.objects.filter(pk=new_id).exists() and not EventService.objects.filter(pk=new_id).exists():
            return new_id

class EventService(models.Model):
    SERVICE_CHOICES = [
        ('photography', 'Photography'),
        ('videography', 'Videography'),
        ('hall_booking', 'Hall Booking'),
        ('sound_system', 'Sound System (DJ)'),
        ('lighting', 'Lighting'),
        ('chef_booking', 'Chef Booking'),
        ('catering', 'Catering'),
    ]
    id = models.CharField(
        primary_key=True,
        default=generate_unique_id,  
        max_length=8
    )
    service_type = models.CharField(
        max_length=50,
        choices=SERVICE_CHOICES,
        db_index=True,
        default='photography'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_service_type_display()


class Event(models.Model):
    id = models.CharField(
        primary_key=True,
        default=generate_unique_id, 
        editable=False,
        max_length=8
    )
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=255, unique=True, db_index=True)
    description = models.TextField()
    logo = models.URLField(blank=True, null=True)
    brand_name = models.CharField(max_length=100, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    total_views = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    daily_reviews = models.JSONField(default=dict)
    
    daily_ratings = models.JSONField(default=dict)
    daily_views = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['seller', 'is_active']),
            models.Index(fields=['brand_name']),
        ]

    def save(self, *args, **kwargs):
        base = slugify(self.brand_name) or "event"
        if not self.slug or not self.slug.startswith(base):
            candidate = base
            i = 0
            while Event.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                i += 1
                suffix = f"-{(self.id or 'new')[:4]}" if i == 1 else f"-{(self.id or 'new')[:4]}-{i}"
                candidate = f"{base}{suffix}"
            self.slug = candidate
        
        # Clean daily views to keep only last 30 days
        self.clean_daily_views()
        super().save(*args, **kwargs)

    def update_daily_stats(self, stat_type):
        today = timezone.now().date().isoformat()
        if stat_type == 'view':
            self.total_views += 1
            self.daily_views[today] = self.daily_views.get(today, 0) + 1
            self.save()

    def clean_daily_views(self):
        """Keep only the last 30 days of view data"""
        if not self.daily_views:
            return
            
        thirty_days_ago = (timezone.now() - timedelta(days=30)).date().isoformat()
        self.daily_views = {
            date: count for date, count in self.daily_views.items() 
            if date >= thirty_days_ago
        }

    def get_daily_views_30d(self):
        """Return only the last 30 days of view data"""
        thirty_days_ago = (timezone.now() - timedelta(days=30)).date().isoformat()
        return {
            date: count for date, count in self.daily_views.items() 
            if date >= thirty_days_ago
        }

    @property
    def total_reviews(self):
        return self.reviews.count()

    @property
    def average_rating(self):
        from django.db.models import Avg
        result = self.reviews.aggregate(avg_rating=Avg('rating'))
        return float(result['avg_rating'] or 0.00)

    def __str__(self):
        return f"{self.brand_name} - {self.title}"


class EventServiceDetail(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='service_details')
    service = models.ForeignKey(EventService, on_delete=models.CASCADE)
    short_description = models.TextField(max_length=500)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)])
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['event', 'service'], name='uniq_event_service'),
        ]

    def __str__(self):
        return f"{self.event.title} - {self.service.get_service_type_display()}"


class EventGallery(models.Model):
    MAX_IMAGES_PER_EVENT = 10

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.URLField() 
    is_primary = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=1)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Event Galleries'
        ordering = ['position', '-is_primary', 'uploaded_at']
        indexes = [
            models.Index(fields=['event', 'position']),
            models.Index(fields=['event', 'is_primary'])
        ]
        constraints = [
            UniqueConstraint(fields=['event', 'position'], name='uniq_event_gallery_position'),
        ]

    def clean(self):
        if not self.pk and EventGallery.objects.filter(event=self.event).count() >= self.MAX_IMAGES_PER_EVENT:
            raise ValidationError(f"Cannot add more than {self.MAX_IMAGES_PER_EVENT} images to an event")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        if self.is_primary:
            EventGallery.objects.filter(event=self.event, is_primary=True).exclude(pk=self.pk).update(is_primary=False)

    def __str__(self):
        return f"Image for {self.event.title} (pos {self.position})"