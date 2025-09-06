from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from django.db import models
from .models import Event, EventService, EventServiceDetail, EventGallery
from apps.users.models import User
from apps.reviews.models import Review
from datetime import timedelta

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    profile_slug = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'whatsapp_click_count','whatsapp_daily_click_count',
                 'profile_image', 'phone_number','whatsapp_number','profile_slug', 'is_verified']
        read_only_fields = fields

    def get_profile_slug(self, obj):
        return obj.get_profile_slug()
    
    
class ReviewSummarySerializer(serializers.ModelSerializer):
    user_full_name = serializers.SerializerMethodField()
    user_profile_image = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = ['id', 'user_full_name', 'user_profile_image', 'rating', 'comment', 'created_at']
    
    def get_user_full_name(self, obj):
        return obj.user.get_full_name()
    
    def get_user_profile_image(self, obj):
        return obj.user.profile_image

class EventServiceRefField(serializers.Field):
    def to_internal_value(self, data):
        try:
            if isinstance(data, str):
                if ' ' in data:  
                    data = data.lower().replace(' ', '_')
                
                service = EventService.objects.filter(service_type__iexact=data).first()
                if service:
                    return service
                
                return EventService.objects.get(pk=data)
            
            if isinstance(data, EventService):
                return data
                
            raise ValueError("Invalid service reference")
        except EventService.DoesNotExist:
            raise serializers.ValidationError(
                f"Service with type or ID '{data}' does not exist."
            )
        except (TypeError, ValueError) as e:
            raise serializers.ValidationError(str(e))
    
    def to_representation(self, value):
        if isinstance(value, EventService):
            return value.service_type
        return value

class EventServiceDetailSerializer(serializers.ModelSerializer):
    service = EventServiceRefField()

    class Meta:
        model = EventServiceDetail
        fields = ['service', 'short_description', 'price', 'is_available']

    def validate_price(self, value):
        if value is None:
            return 0.00  
        return value


class EventGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = EventGallery
        fields = ['image', 'position', 'is_primary']


class EventSerializer(serializers.ModelSerializer):
    seller_info = UserSerializer(source='seller', read_only=True)
    reviews = serializers.SerializerMethodField()
    service_details = EventServiceDetailSerializer(many=True, required=False)
    gallery_images = EventGallerySerializer(many=True, required=False)
    
    # Add computed fields
    total_reviews = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    daily_reviews = serializers.SerializerMethodField()
    daily_ratings = serializers.SerializerMethodField()
    daily_views = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'seller','seller_info', 'title', 'slug', 'description', 'logo', 'brand_name',
            'is_active', 'total_views', 'total_reviews', 'average_rating',
            'daily_views', 'daily_reviews', 'daily_ratings',
            'created_at', 'updated_at',
            'service_details', 'gallery_images',"reviews"
        ]
        read_only_fields = [
            'seller', 'total_views', 'created_at', 'updated_at',
        ]

    def get_total_reviews(self, obj):
        return obj.reviews.count()

    def get_average_rating(self, obj):
        return obj.reviews.aggregate(avg=models.Avg('rating'))['avg'] or 0.00
        
    def get_reviews(self, obj):
        reviews = obj.reviews.all().order_by('-created_at')[:10]
        return ReviewSummarySerializer(reviews, many=True, context=self.context).data

    def get_daily_reviews(self, obj):
        """Calculate daily reviews for the last 30 days"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        daily_counts = (
            obj.reviews
            .filter(created_at__gte=thirty_days_ago)
            .extra(select={'day': "date(created_at)"})
            .values('day')
            .annotate(count=models.Count('id'))
            .order_by('day')
        )
        
        return {item['day'].isoformat() if hasattr(item['day'], 'isoformat') else str(item['day']): item['count'] for item in daily_counts}

    def get_daily_ratings(self, obj):
        """Calculate daily average ratings for the last 30 days"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        daily_avgs = (
            obj.reviews
            .filter(created_at__gte=thirty_days_ago)
            .extra(select={'day': "date(created_at)"})
            .values('day')
            .annotate(avg_rating=models.Avg('rating'))
            .order_by('day')
        )
        
        return {item['day'].isoformat() if hasattr(item['day'], 'isoformat') else str(item['day']): float(item['avg_rating'] or 0) for item in daily_avgs}

    def get_daily_views(self, obj):
        """Return only the last 30 days of views"""
        return obj.get_daily_views_30d()

    def validate_gallery_images(self, items):
        if items and len(items) > EventGallery.MAX_IMAGES_PER_EVENT:
            raise serializers.ValidationError(
                f"Maximum {EventGallery.MAX_IMAGES_PER_EVENT} images are allowed."
            )
        positions = [it.get('position') for it in items if it.get('position') is not None]
        if len(positions) != len(set(positions)):
            raise serializers.ValidationError("Each image must have a unique position within the event.")
        return items

    def _upsert_service_details(self, event, details):
        existing_map = {sd.service_id: sd for sd in event.service_details.all()}
        sent_ids = set()

        for item in details:
            service = item['service']
            obj = existing_map.get(str(service.pk)) or existing_map.get(service.pk) or existing_map.get(service.id)
            if obj:
                for field in ['short_description', 'price', 'is_available']:
                    if field in item:
                        setattr(obj, field, item[field])
                obj.save()
            else:
                EventServiceDetail.objects.create(
                    event=event,
                    service=service,
                    short_description=item.get('short_description', ''),
                    price=item.get('price', 0.00), 
                    is_available=item.get('is_available', True),
                )
            sent_ids.add(service.id)

        if not self.partial:
            EventServiceDetail.objects.filter(event=event).exclude(service_id__in=sent_ids).delete()

    def _replace_gallery_images(self, event, images):
        if images is None:
            return

        if not self.partial:
            event.gallery_images.all().delete()

        by_position = {}
        for img in images:
            pos = img.get('position')
            if pos is None:
                raise serializers.ValidationError("Each gallery image must include 'position'.")
            if pos in by_position:
                raise serializers.ValidationError("Duplicate positions in payload are not allowed.")
            by_position[pos] = img

        new_objs = []
        for pos, data in by_position.items():
            obj, created = EventGallery.objects.update_or_create(
                event=event, position=pos,
                defaults={
                    'image': data['image'],
                    'is_primary': data.get('is_primary', False),
                }
            )
            new_objs.append(obj)

        if any(getattr(o, 'is_primary', False) for o in new_objs):
            EventGallery.objects.filter(event=event, is_primary=True).exclude(pk__in=[o.pk for o in new_objs if o.is_primary]).update(is_primary=False)

        if event.gallery_images.count() > EventGallery.MAX_IMAGES_PER_EVENT:
            raise serializers.ValidationError(
                f"Maximum {EventGallery.MAX_IMAGES_PER_EVENT} images are allowed."
            )

    @transaction.atomic
    def create(self, validated_data):
        service_details = validated_data.pop('service_details', [])
        gallery_images = validated_data.pop('gallery_images', [])
        event = Event.objects.create(**validated_data)

        if service_details:
            sd_serializer = EventServiceDetailSerializer(data=service_details, many=True)
            sd_serializer.is_valid(raise_exception=True)
            self._upsert_service_details(event, sd_serializer.validated_data)

        if gallery_images:
            gi_serializer = EventGallerySerializer(data=gallery_images, many=True)
            gi_serializer.is_valid(raise_exception=True)
            self._replace_gallery_images(event, gi_serializer.validated_data)

        return event

    @transaction.atomic
    def update(self, instance, validated_data):
        service_details = validated_data.pop('service_details', None)  
        gallery_images = validated_data.pop('gallery_images', None)    

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if service_details is not None:
            sd_serializer = EventServiceDetailSerializer(data=service_details, many=True, partial=self.partial)
            sd_serializer.is_valid(raise_exception=True)
            self._upsert_service_details(instance, sd_serializer.validated_data)

        if gallery_images is not None:
            gi_serializer = EventGallerySerializer(data=gallery_images, many=True, partial=self.partial)
            gi_serializer.is_valid(raise_exception=True)
            self._replace_gallery_images(instance, gi_serializer.validated_data)

        return instance
    
       
# ---------- Dashboard Serializers ----------

class RatingBucketSerializer(serializers.Serializer):
    rating = serializers.FloatField()
    count = serializers.IntegerField()

class EventDashboardSerializer(serializers.Serializer):
    id = serializers.CharField()
    slug = serializers.SlugField()
    brand_name = serializers.CharField()
    title = serializers.CharField()

    total_views = serializers.IntegerField()
    today_views = serializers.SerializerMethodField()  
    total_reviews = serializers.SerializerMethodField()  
    average_rating = serializers.FloatField()

    daily_comment_count = serializers.IntegerField()
    daily_average_rating = serializers.FloatField()
    rating_distribution = RatingBucketSerializer(many=True)

    def get_total_reviews(self, obj):
        return obj.reviews.count() 

    def get_today_views(self, obj):  # 👈 Add this
        today_key = timezone.now().date().isoformat()
        return int((obj.daily_views or {}).get(today_key, 0))

    def to_representation(self, instance: Event):
        today_key = timezone.now().date().isoformat()

        rstats = Review.get_dashboard_stats(event_id=instance.id)
        dist_qs = Review.get_rating_distribution(event_id=instance.id)
        dist = [{'rating': float(d['rating']), 'count': d['count']} for d in dist_qs]

        return {
            'id': instance.id,
            'slug': instance.slug,
            'brand_name': instance.brand_name,
            'title': instance.title,
            'total_views': int(instance.total_views or 0),
            'today_views': self.get_today_views(instance), 
            'total_reviews': self.get_total_reviews(instance),
            'average_rating': float(instance.average_rating or 0),
            'daily_comment_count': int(rstats.get('daily_comment_count', 0) or 0),
            'daily_average_rating': float(rstats.get('daily_average_rating', 0) or 0.0),
            'rating_distribution': dist,
        }


class GlobalDashboardSerializer(serializers.Serializer):
    total_events = serializers.IntegerField()
    total_views = serializers.IntegerField()
    today_views = serializers.IntegerField()
    total_reviews = serializers.IntegerField()
    average_rating = serializers.FloatField()
    daily_comment_count = serializers.IntegerField()
    daily_average_rating = serializers.FloatField()
    rating_distribution = RatingBucketSerializer(many=True)

    def to_representation(self, instance):
        """
        instance is ignored; we compute from context.
        Expect context: {'events': queryset_of_events}
        """
        events = self.context.get('events')
        if events is None:
            events = Event.objects.all()

        today_key = timezone.now().date().isoformat()

        total_events = events.count()
        total_views = 0
        today_views = 0
        total_reviews = 0

        for ev in events:
            total_views += int(ev.total_views or 0)
            total_reviews += ev.reviews.count()  
            today_views += int((ev.daily_views or {}).get(today_key, 0))

        rstats = Review.get_dashboard_stats(event_id=None)
        dist_qs = Review.get_rating_distribution(event_id=None)
        dist = [{'rating': float(d['rating']), 'count': d['count']} for d in dist_qs]

        return {
            'total_events': total_events,
            'total_views': total_views,
            'today_views': today_views,
            'total_reviews': total_reviews,
            'average_rating': float(Review.get_average_rating(event_id=None)),
            'daily_comment_count': int(rstats.get('daily_comment_count', 0) or 0),
            'daily_average_rating': float(rstats.get('daily_average_rating', 0) or 0.0),
            'rating_distribution': dist,
        }