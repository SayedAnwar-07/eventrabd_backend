from rest_framework import serializers
from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    user_full_name = serializers.SerializerMethodField(read_only=True)
    user_profile_image = serializers.SerializerMethodField(read_only=True)
    event_brand_name = serializers.SerializerMethodField(read_only=True)
    can_edit = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'user', 'user_full_name','user_profile_image', 'event', 'event_brand_name', 
            'rating', 'comment', 'created_at', 'updated_at', 'can_edit'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'user_full_name', 'user_profile_image', 'event_brand_name']
    
    def get_user_full_name(self, obj):
        return obj.user.get_full_name()
    
    def get_user_profile_image(self, obj):
        return obj.user.profile_image
    
    def get_event_brand_name(self, obj):
        return obj.event.brand_name
    
    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return obj.user == request.user
        return False
    
    def validate_rating(self, value):
        """Validate that rating is within allowed choices"""
        allowed_ratings = [choice[0] for choice in Review.RATING_CHOICES]
        if value not in allowed_ratings:
            raise serializers.ValidationError(
                f'Rating must be one of: {", ".join(str(r) for r in allowed_ratings)}'
            )
        return value
    
    def validate(self, data):
        """Validate that user hasn't already reviewed this event"""
        request = self.context.get('request')
        
        if request and self.instance is None:  #
            user = request.user
            event = data.get('event') or (self.instance.event if self.instance else None)
            
            if event and Review.objects.filter(user=user, event=event).exists():
                raise serializers.ValidationError({
                    'event': 'You have already reviewed this event.'
                })
        
        return data
    
    def create(self, validated_data):
        """Create a new review with the current user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['user'] = request.user
        
        return super().create(validated_data)

class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['rating', 'comment'] 
    
    def validate_rating(self, value):
        """Validate that rating is within allowed choices"""
        allowed_ratings = [choice[0] for choice in Review.RATING_CHOICES]
        if value not in allowed_ratings:
            raise serializers.ValidationError(
                f'Rating must be one of: {", ".join(str(r) for r in allowed_ratings)}'
            )
        return value
    
    def create(self, validated_data):
        """Create a new review with the current user and event from URL"""
        request = self.context.get('request')
        view = self.context.get('view')
        
        if request and hasattr(request, 'user'):
            validated_data['user'] = request.user
        
        # Get event from URL parameters
        if view and hasattr(view, 'kwargs'):
            event_slug = view.kwargs.get('event_slug')
            if event_slug:
                from apps.events.models import Event
                event = Event.objects.get(slug=event_slug)
                validated_data['event'] = event
        
        return super().create(validated_data)

class ReviewUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
    
    def validate_rating(self, value):
        """Validate that rating is within allowed choices"""
        allowed_ratings = [choice[0] for choice in Review.RATING_CHOICES]
        if value not in allowed_ratings:
            raise serializers.ValidationError(
                f'Rating must be one of: {", ".join(str(r) for r in allowed_ratings)}'
            )
        return value

class EventReviewStatsSerializer(serializers.Serializer):
    average_rating = serializers.FloatField()
    total_comments = serializers.IntegerField()
    daily_comment_count = serializers.IntegerField()
    daily_average_rating = serializers.FloatField()
    rating_distribution = serializers.ListField()

class ReviewSummarySerializer(serializers.ModelSerializer):
    user_full_name = serializers.SerializerMethodField()
    event_brand_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = ['id', 'user_full_name','user_profile_image', 'event_brand_name', 'rating', 'comment', 'created_at']
    
    def get_user_full_name(self, obj):
        return obj.user.get_full_name()
    
    def get_event_brand_name(self, obj):
        return obj.event.brand_name