from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F

from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    PermissionDenied,
)
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.core.responses import success_response
from apps.event_planner.models import EventBrand
from apps.event_services.models import EventService
from apps.hires.models import Hire, HireStatus

from .models import Review
from .serializers import (
    ReviewCreateSerializer,
    ReviewDetailSerializer,
    ReviewUpdateSerializer,
)


# =========================================================
# Pagination
# =========================================================

class ReviewPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 20


# =========================================================
# Review CRUD
# =========================================================

class ReviewViewSet(GenericViewSet):
    """
    POST:
        Create review.

    GET /{id}/:
        Public review detail.

    PATCH /{id}/:
        Customer updates own review.

    DELETE /{id}/:
        Customer deletes own review.
        Staff / superuser can also delete.
    """

    queryset = (
        Review.objects
        .select_related(
            "hire",
            "hire__customer",
            "hire__service",
            "hire__service__brand",
        )
        .order_by("-created_at")
    )

    lookup_field = "id"

    http_method_names = [
        "get",
        "post",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_serializer_class(self):
        if self.action == "create":
            return ReviewCreateSerializer

        if self.action == "partial_update":
            return ReviewUpdateSerializer

        return ReviewDetailSerializer

    def get_permissions(self):
        if self.action == "retrieve":
            return [AllowAny()]

        return [IsAuthenticated()]

    # -----------------------------------------------------
    # Create
    # -----------------------------------------------------

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        review = serializer.save()

        response_serializer = ReviewDetailSerializer(
            review,
            context=self.get_serializer_context(),
        )

        return success_response(
            message="Review submitted successfully.",
            data=response_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )

    # -----------------------------------------------------
    # Retrieve
    # -----------------------------------------------------

    def retrieve(self, request, *args, **kwargs):
        review = self.get_object()

        serializer = ReviewDetailSerializer(
            review,
            context=self.get_serializer_context(),
        )

        return success_response(
            message="Review retrieved successfully.",
            data=serializer.data,
        )

    # -----------------------------------------------------
    # Update
    # -----------------------------------------------------

    def partial_update(
        self,
        request,
        *args,
        **kwargs,
    ):
        review = self.get_object()

        serializer = ReviewUpdateSerializer(
            review,
            data=request.data,
            partial=True,
            context=self.get_serializer_context(),
        )

        serializer.is_valid(
            raise_exception=True,
        )

        updated_review = serializer.save()

        response_serializer = ReviewDetailSerializer(
            updated_review,
            context=self.get_serializer_context(),
        )

        return success_response(
            message="Review updated successfully.",
            data=response_serializer.data,
        )

    # -----------------------------------------------------
    # Delete
    # -----------------------------------------------------

    def destroy(
        self,
        request,
        *args,
        **kwargs,
    ):
        review_id = kwargs.get(
            self.lookup_field,
        )

        with transaction.atomic():
            try:
                review = (
                    Review.objects
                    .select_for_update()
                    .select_related(
                        "hire",
                        "hire__customer",
                        "hire__service",
                        "hire__service__brand",
                    )
                    .get(
                        pk=review_id,
                    )
                )

            except Review.DoesNotExist:
                raise NotFound(
                    "Review was not found."
                )

            user = request.user

            is_owner = (
                review.hire.customer_id
                == user.id
            )

            is_admin = (
                user.is_staff
                or user.is_superuser
            )

            if not is_owner and not is_admin:
                raise PermissionDenied(
                    "You cannot delete another customer's review."
                )

            # -------------------------------------------------
            # Store required values BEFORE deleting the review
            # -------------------------------------------------

            rating = review.rating
            service_id = review.hire.service_id
            brand_id = review.hire.service.brand_id

            # -------------------------------------------------
            # Service rating statistics
            # -------------------------------------------------

            service_updated = (
                EventService.objects
                .filter(
                    pk=service_id,
                    review_count__gte=1,
                    rating_sum__gte=rating,
                )
                .update(
                    rating_sum=(
                        F("rating_sum") - rating
                    ),
                    review_count=(
                        F("review_count") - 1
                    ),
                )
            )

            if service_updated != 1:
                raise APIException(
                    "Service review statistics are inconsistent."
                )

            # -------------------------------------------------
            # Brand rating statistics
            # -------------------------------------------------

            brand_updated = (
                EventBrand.objects
                .filter(
                    pk=brand_id,
                    review_count__gte=1,
                    rating_sum__gte=rating,
                )
                .update(
                    rating_sum=(
                        F("rating_sum") - rating
                    ),
                    review_count=(
                        F("review_count") - 1
                    ),
                )
            )

            if brand_updated != 1:
                raise APIException(
                    "Brand review statistics are inconsistent."
                )

            # -------------------------------------------------
            # Delete review only after statistics updated
            # -------------------------------------------------

            review.delete()

        return success_response(
            message="Review deleted successfully.",
            data={},
        )


# =========================================================
# Service review list
# =========================================================

class ServiceReviewListView(GenericAPIView):
    """
    Public paginated reviews for one service.

    Example:
        /services/<service_id>/reviews/?page=1
    """

    permission_classes = [
        AllowAny,
    ]

    serializer_class = ReviewDetailSerializer
    pagination_class = ReviewPagination

    def get_queryset(self):
        service_id = self.kwargs[
            "service_id"
        ]

        return (
            Review.objects
            .filter(
                hire__service_id=service_id,
            )
            .select_related(
                "hire",
                "hire__customer",
                "hire__service",
                "hire__service__brand",
            )
            .order_by("-created_at")
        )

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(
            queryset
        )

        if page is not None:
            serializer = self.get_serializer(
                page,
                many=True,
            )

            paginator = self.paginator

            data = {
                "count": (
                    paginator
                    .page
                    .paginator
                    .count
                ),
                "next": paginator.get_next_link(),
                "previous": (
                    paginator.get_previous_link()
                ),
                "results": serializer.data,
            }

            return success_response(
                message="Reviews retrieved successfully.",
                data=data,
            )

        serializer = self.get_serializer(
            queryset,
            many=True,
        )

        return success_response(
            message="Reviews retrieved successfully.",
            data={
                "count": len(serializer.data),
                "next": None,
                "previous": None,
                "results": serializer.data,
            },
        )


# =========================================================
# Review eligibility
# =========================================================

class HireReviewEligibilityView(APIView):
    """
    Frontend helper endpoint.

    This is NOT the security check.

    ReviewCreateSerializer will again validate
    eligibility during POST.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    def get(
        self,
        request,
        hire_id,
    ):
        user = request.user

        if getattr(
            user,
            "role",
            None,
        ) != "customer":
            raise PermissionDenied(
                "Only customers can check review eligibility."
            )

        try:
            hire = (
                Hire.objects
                .select_related(
                    "customer",
                    "service",
                    "invoice",
                    "review",
                )
                .get(
                    pk=hire_id,
                )
            )

        except Hire.DoesNotExist:
            raise NotFound(
                "Hire request was not found."
            )

        if hire.customer_id != user.id:
            raise PermissionDenied(
                "You cannot check another customer's hire."
            )

        # -------------------------------------------------
        # Existing review
        # -------------------------------------------------

        try:
            existing_review = hire.review

        except ObjectDoesNotExist:
            existing_review = None

        # -------------------------------------------------
        # Invoice
        # -------------------------------------------------

        try:
            invoice = hire.invoice

        except ObjectDoesNotExist:
            invoice = None

        can_review = (
            hire.status == HireStatus.COMPLETED
            and invoice is not None
            and invoice.customer_agreed is True
            and existing_review is None
        )

        service_ids = (
            [str(hire.service_id)]
            if can_review
            else []
        )

        return success_response(
            message="Review eligibility retrieved successfully.",
            data={
                "can_review": can_review,
                "service_ids": service_ids,
                "review_id": (
                    str(existing_review.id)
                    if existing_review
                    else None
                ),
            },
        )