from rest_framework import serializers
from apps.reports.models import Report, ReportImage
from apps.events.models import Event
from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    profile_slug = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name',
                 'profile_image', 'phone_number','whatsapp_number','profile_slug']
        read_only_fields = fields

    def get_profile_slug(self, obj):
        return obj.get_profile_slug()
    

class ReportImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportImage
        fields = ['id', 'image', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']


class ReportSerializer(serializers.ModelSerializer):
    """
    Write API:
      - Provide: event (id), description, user_full_name, phone_number
      - Optionally provide up to 3 images via `images` (list of URLs)
    """
    images = serializers.ListField(
        child=serializers.URLField(),
        write_only=True,
        required=False,
        allow_empty=True,
        max_length=ReportImage.MAX_IMAGES_PER_REPORT
    )
    images_list = ReportImageSerializer(source='images', many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    status_changed_by_name = serializers.CharField(
        source='status_changed_by.get_full_name', 
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Report
        fields = [
            'id',
            'event',
            'description',
            'user_full_name',
            'phone_number',
            'brand_name',
            'seller_full_name',
            'seller',
            'reporter',
            'status',
            'status_display',
            'status_changed_at',
            'status_changed_by',
            'status_changed_by_name',
            'admin_notes',
            'created_at',
            'updated_at',
            'images',
            'images_list',
        ]
        read_only_fields = [
            'id',
            'brand_name',
            'seller_full_name',
            'seller',
            'reporter',
            'status',
            'status_changed_at',
            'status_changed_by',
            'admin_notes',
            'created_at',
            'updated_at',
        ]

    def validate_event(self, value):
        # Convert event ID to Event instance if needed
        if isinstance(value, str):
            try:
                return Event.objects.get(id=value)
            except Event.DoesNotExist:
                raise serializers.ValidationError("Event does not exist.")
        return value

    def validate(self, attrs):
        images = attrs.get('images', [])
        if len(images) > ReportImage.MAX_IMAGES_PER_REPORT:
            raise serializers.ValidationError(
                {"images": f"Max {ReportImage.MAX_IMAGES_PER_REPORT} images are allowed."}
            )
        return attrs

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        
        # Hide admin-only fields for non-admin users
        if request and not request.user.is_staff:
            representation.pop('admin_notes', None)
            representation.pop('status_changed_by', None)
            representation.pop('status_changed_by_name', None)
        
        return representation

    def create(self, validated_data):
        images = validated_data.pop('images', [])
        event = validated_data.pop('event')
        
        # Auto-fill denormalized fields from event
        report = Report.objects.create(
            event=event,
            seller=event.seller,
            brand_name=event.brand_name,
            seller_full_name=event.seller.full_name,
            reporter=self.context['request'].user,
            **validated_data
        )

        # Create images
        for url in images[:ReportImage.MAX_IMAGES_PER_REPORT]:
            ReportImage.objects.create(report=report, image=url)

        return report


class AdminReportStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for admin-only status updates
    """
    class Meta:
        model = Report
        fields = ['status', 'admin_notes']
    
    def update(self, instance, validated_data):
        request = self.context.get('request')
        if request and request.user.is_staff:
            instance.status_changed_by = request.user
        return super().update(instance, validated_data)