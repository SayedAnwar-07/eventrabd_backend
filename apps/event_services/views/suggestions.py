from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.users.models import User
from apps.event_planner.models import EventBrand

from apps.event_services.serializers.suggestions import (
    SellerSuggestionSerializer,
    BrandSuggestionSerializer,
)


class SellerSuggestionView(ListAPIView):

    serializer_class = SellerSuggestionSerializer

    permission_classes = [
        AllowAny,
    ]

    def get_queryset(self):

        q = (
            self.request
            .query_params
            .get("q", "")
            .strip()
        )

        print("SELLER SEARCH HIT:", q)

        if not q:
            return User.objects.none()


        queryset = (
            User.objects
            .filter(
                role="seller",
                is_active=True,
                full_name__icontains=q,
            )
            .order_by(
                "full_name"
            )[:10]
        )

        return queryset



class BrandSuggestionView(ListAPIView):

    serializer_class = BrandSuggestionSerializer

    permission_classes = [
        AllowAny,
    ]


    def get_queryset(self):

        q = (
            self.request
            .query_params
            .get("q", "")
            .strip()
        )

        if not q:
            return EventBrand.objects.none()


        return (
            EventBrand.objects
            .filter(
                display_name__icontains=q
            )
            .order_by(
                "display_name"
            )[:10]
        )