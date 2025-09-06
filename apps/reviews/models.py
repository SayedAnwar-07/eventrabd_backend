from django.db import models
from django.conf import settings
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.events.models import Event
from django.utils.crypto import get_random_string

def generate_unique_id():
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    while True:
        new_id = get_random_string(8, allowed_chars=alphabet)
        if not Event.objects.filter(pk=new_id).exists() and not Review.objects.filter(pk=new_id).exists():
            return new_id

class Review(models.Model):
    RATING_CHOICES = [
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5'),
    ]

    
    id = models.CharField(
        primary_key=True,
        default=generate_unique_id,  
        max_length=8
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='reviews'
    )
    event = models.ForeignKey(
        Event, 
        on_delete=models.CASCADE, 
        related_name='reviews'
    )
    rating = models.FloatField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'event']
        ordering = ['-created_at']
        verbose_name = 'Review'
        verbose_name_plural = 'Reviews'
    
    def clean(self):
        # Validate that rating is within allowed choices
        allowed_ratings = [choice[0] for choice in self.RATING_CHOICES]
        if self.rating not in allowed_ratings:
            raise ValidationError({
                'rating': f'Rating must be one of: {", ".join(str(r) for r in allowed_ratings)}'
            })
    
    def save(self, *args, **kwargs):
        self.full_clean()  # Run validation before saving
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.event.brand_name} ({self.rating})"
    
    @classmethod
    def get_average_rating(cls, event_id=None):
        queryset = cls.objects.all()
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        result = queryset.aggregate(avg_rating=Avg('rating'))
        return round(result['avg_rating'] or 0, 2)  # Changed to 2 decimal places
    
    @classmethod
    def get_total_comments(cls, event_id=None):
        queryset = cls.objects.all()
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset.count()
    
    @classmethod
    def get_daily_stats(cls, event_id=None):
        today = timezone.now().date()
        start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        
        queryset = cls.objects.filter(created_at__gte=start_of_day)
        if event_id:
            queryset = queryset.filter(event_id=event_id)
            
        result = queryset.aggregate(
            comment_count=Count('id'),
            avg_rating=Avg('rating')
        )
        
        return {
            'comment_count': result['comment_count'] or 0,
            'avg_rating': round(result['avg_rating'] or 0, 2) if result['avg_rating'] is not None else 0.0
        }
    
    @classmethod
    def get_rating_distribution(cls, event_id=None):
        queryset = cls.objects.all()
        if event_id:
            queryset = queryset.filter(event_id=event_id)
            
        distribution = queryset.values('rating').annotate(
            count=Count('id')
        ).order_by('rating')
        
        # Ensure all ratings 1-5 are represented
        rating_dist = {float(rating): 0 for rating in range(1, 6)}
        for item in distribution:
            rating_dist[float(item['rating'])] = item['count']
        
        return [{'rating': rating, 'count': count} for rating, count in rating_dist.items()]
    
    @classmethod
    def get_dashboard_stats(cls, event_id=None):
        daily_stats = cls.get_daily_stats(event_id)
        
        return {
            'average_rating': cls.get_average_rating(event_id),
            'total_comments': cls.get_total_comments(event_id),
            'daily_comment_count': daily_stats['comment_count'],
            'daily_average_rating': daily_stats['avg_rating'],
            'rating_distribution': cls.get_rating_distribution(event_id),
        }