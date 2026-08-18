from rest_framework import serializers

from apps.event_services.models import EventService


# =========================================================
# Admin service serializer
# =========================================================


class AdminServiceSerializer(
    serializers.ModelSerializer
):
    service_display_name = serializers.CharField(
        source="get_service_name_display",
        read_only=True,
    )

    # -----------------------------------------------------
    # Brand
    # -----------------------------------------------------

    brand_name = serializers.CharField(
        source="brand.brand_name",
        read_only=True,
    )

    brand_display_name = serializers.CharField(
        source="brand.display_name",
        read_only=True,
    )

    # -----------------------------------------------------
    # Seller
    # -----------------------------------------------------

    seller_id = serializers.CharField(
        source="brand.seller.id",
        read_only=True,
    )

    seller_name = serializers.CharField(
        source="brand.seller.full_name",
        read_only=True,
    )

    seller_email = serializers.EmailField(
        source="brand.seller.email",
        read_only=True,
    )

    seller_whatsapp_number = serializers.CharField(
        source="brand.seller.whatsapp_number",
        read_only=True,
    )

    seller_contact_number = serializers.CharField(
        source="brand.seller.contact_number",
        read_only=True,
    )

    # -----------------------------------------------------
    # Rating
    # -----------------------------------------------------

    rating = serializers.DecimalField(
        source="average_rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = EventService

        fields = [
            "id",

            # Service
            "service_name",
            "service_display_name",
            "slug",

            # Brand
            "brand_name",
            "brand_display_name",

            # Seller
            "seller_id",
            "seller_name",
            "seller_email",
            "seller_whatsapp_number",
            "seller_contact_number",

            # Rating / reviews / reports
            "rating",
            "rating_sum",
            "review_count",
            "report_count",

            # Date
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields