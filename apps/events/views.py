from rest_framework import generics, permissions, status, serializers 
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import Event
from apps.users.models import User
from .serializers import EventSerializer,EventDashboardSerializer, GlobalDashboardSerializer,EventService
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import models



class IsSellerOrReadOnly(permissions.BasePermission):
    """
    Only the event.owner (seller) can update/delete.
    Everyone can read.
    """
    def has_object_permission(self, request, view, obj: Event):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.seller_id == getattr(request.user, "id", None)


class CreateEvents(generics.CreateAPIView):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        seller = self.request.user
        if Event.objects.filter(seller=seller).exists():
            raise serializers.ValidationError({"error": "You are only allowed to create one event."})

        if Event.objects.filter(brand_name=serializer.validated_data['brand_name']).exists():
            raise serializers.ValidationError({"error": "Brand name must be unique."})
        
        serializer.save(seller=seller)

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class DetailsEvent(generics.RetrieveAPIView):
    serializer_class = EventSerializer
    queryset = Event.objects.select_related("seller").prefetch_related("service_details", "gallery_images")
    lookup_field = "slug"
    permission_classes = [permissions.AllowAny]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count here
        instance.update_daily_stats("view")
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

class AllEventsView(generics.ListAPIView):
    """
    GET /events/
    Retrieve all active events with optional filtering and pagination.
    """
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]
    queryset = (
        Event.objects.filter(is_active=True)
        .select_related("seller")
        .prefetch_related("service_details", "gallery_images")
    )
    lookup_field = "slug"

    def get_queryset(self):
        queryset = super().get_queryset()

        # --- Filters ---
        service_types = self.request.query_params.getlist("service_type")
        if service_types:
            service_q = models.Q()
            for service_type in service_types:
                service_q |= models.Q(service_details__service__service_type=service_type)
            queryset = queryset.filter(service_q)

        search_query = (self.request.query_params.get("search") or "").strip()
        if search_query:

            queryset = queryset.filter(
                models.Q(title__icontains=search_query)
                | models.Q(brand_name__icontains=search_query)
                | models.Q(seller__first_name__icontains=search_query)
                | models.Q(seller__last_name__icontains=search_query)
            )

        brand_name = self.request.query_params.get("brand_name")
        if brand_name:
            queryset = queryset.filter(brand_name__icontains=brand_name)

        seller_name = self.request.query_params.get("seller_name")
        if seller_name:
            parts = [p for p in seller_name.split() if p]
            if len(parts) >= 2:
                queryset = queryset.filter(
                    models.Q(seller__first_name__icontains=parts[0]) |
                    models.Q(seller__last_name__icontains=parts[-1])
                )
            else:
                queryset = queryset.filter(
                    models.Q(seller__first_name__icontains=seller_name) |
                    models.Q(seller__last_name__icontains=seller_name)
                )

        title = self.request.query_params.get("title")
        if title:
            queryset = queryset.filter(title__icontains=title)

        min_rating = self.request.query_params.get("min_rating")
        if min_rating:
            try:
                queryset = queryset.filter(average_rating__gte=float(min_rating))
            except (ValueError, TypeError):
                pass

        if service_types or search_query:  
            queryset = queryset.distinct()

        # Ordering
        order_by = self.request.query_params.get("order_by", "-created_at")
        if order_by in [
            "created_at",
            "-created_at",
            "average_rating",
            "-average_rating",
            "total_views",
            "-total_views",
            "brand_name",
            "-brand_name",
        ]:
            queryset = queryset.order_by(order_by)

        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        # attach suggestions when search present (non-breaking for FE)
        search_query = (request.query_params.get("search") or "").strip()
        if search_query:
            suggestions = self.get_search_suggestions(search_query)
            # DRF pagination returns OrderedDict; mutate safely
            data = response.data
            try:
                data["suggestions"] = suggestions
            except TypeError:
                # non-paginated (list)
                response.data = {"results": data, "count": len(data), "suggestions": suggestions}
        return response

    def get_search_suggestions(self, query):
        q = (query or "").lower().strip()
        suggestions = {
            "brand_names": [],
            "seller_names": [],
            "service_types": [],
            "popular_searches": [],
        }

        # Brand names
        brand_suggestions = (
            Event.objects.filter(is_active=True, brand_name__icontains=q)
            .values_list("brand_name", flat=True)
            .distinct()[:5]
        )
        suggestions["brand_names"] = list(brand_suggestions)

        # Seller names
        seller_suggestions = (
            User.objects.filter(
                models.Q(first_name__icontains=q)
                | models.Q(last_name__icontains=q)
                | models.Q(email__icontains=q)
            )
            .values_list("first_name", "last_name")[:5]
        )
        suggestions["seller_names"] = [
            f"{fn} {ln}".strip() for fn, ln in seller_suggestions
        ]

        # Service types
        service_matches = []
        for code, name in EventService.SERVICE_CHOICES:
            if q in name.lower() or q in code.lower():
                service_matches.append(name)
        suggestions["service_types"] = service_matches[:5]

        # Popular (first-letter)
        suggestions["popular_searches"] = self.get_popular_searches(q)
        return suggestions

    def get_popular_searches(self, current_query):
        popular_terms = {
            "w": ["wedding", "wedding photography", "wedding catering"],
            "p": ["photography", "portrait photography", "product photography"],
            "c": ["catering", "corporate events", "chef booking"],
            "v": ["videography", "video production", "video editing"],
            "d": ["dj services", "sound system", "lighting"],
            "h": ["hall booking", "hotel venues", "hall decoration"],
        }
        first_char = (current_query or "")[:1]
        return popular_terms.get(first_char, [])[:3]

class SearchSuggestionsView(APIView):
    """
    GET /events/suggestions/?q=query
    Returns search suggestions for the given query
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 1:
            return Response({"suggestions": {}}, status=status.HTTP_200_OK)
        return Response({"suggestions": self.generate_suggestions(query)}, status=status.HTTP_200_OK)

    def generate_suggestions(self, query):
        q = (query or "").lower().strip()
        suggestions = {
            "brand_names": [],
            "seller_names": [],
            "service_types": [],
            "popular_searches": [],  
        }

        # Brand names
        brand_suggestions = (
            Event.objects.filter(is_active=True, brand_name__icontains=q)
            .values_list("brand_name", flat=True)
            .distinct()[:5]
        )
        suggestions["brand_names"] = list(brand_suggestions)

        # Seller names
        seller_suggestions = (
            User.objects.filter(
                models.Q(first_name__icontains=q) | models.Q(last_name__icontains=q)
            )
            .values("first_name", "last_name")[:5]
        )
        suggestions["seller_names"] = [
            f"{u['first_name']} {u['last_name']}".strip() for u in seller_suggestions
        ]

        # Service types
        service_matches = []
        for code, name in EventService.SERVICE_CHOICES:
            if q in name.lower() or q in code.lower():
                service_matches.append(name)
        suggestions["service_types"] = service_matches[:5]

        popular_terms = {
            "w": ["wedding", "wedding photography", "wedding catering"],
            "p": ["photography", "portrait photography", "product photography"],
            "c": ["catering", "corporate events", "chef booking"],
            "v": ["videography", "video production", "video editing"],
            "d": ["dj services", "sound system", "lighting"],
            "h": ["hall booking", "hotel venues", "hall decoration"],
        }
        first_char = (query or "")[:1]
        suggestions["popular_searches"] = popular_terms.get(first_char, [])[:3]

        return suggestions

class UpdateEvent(generics.UpdateAPIView):
    serializer_class = EventSerializer
    queryset = Event.objects.all()
    lookup_field = "slug"
    permission_classes = [permissions.IsAuthenticated, IsSellerOrReadOnly]
    http_method_names = ["patch"]
    parser_classes = [JSONParser, MultiPartParser, FormParser] 

    def get_object(self):
        obj = get_object_or_404(
            self.get_queryset().select_related('seller')
                              .prefetch_related('service_details__service', 'gallery_images'),
            slug=self.kwargs["slug"]
        )
        self.check_object_permissions(self.request, obj)
        return obj

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class DeleteEvents(generics.DestroyAPIView):
    """
    DELETE /events/<slug>/
    Delete an event by slug.
    """
    serializer_class = EventSerializer
    queryset = Event.objects.all()
    lookup_field = "slug"
    permission_classes = [permissions.IsAuthenticated, IsSellerOrReadOnly]
    
    
class EventDashboardView(APIView):
    """
    GET /events/<slug:slug>/dashboard/
    Returns dashboard data for a single event.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug, *args, **kwargs):
        event = get_object_or_404(Event, slug=slug, is_active=True)
        payload = EventDashboardSerializer(event).data
        return Response(payload, status=status.HTTP_200_OK)


class GlobalDashboardView(APIView):
    """
    GET /events/dashboard/
    Returns aggregated dashboard data across all events.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        events = Event.objects.filter(is_active=True)
        serializer = GlobalDashboardSerializer(instance=None, context={'events': events})
        return Response(serializer.data, status=status.HTTP_200_OK)