from django.urls import include, path

from rest_framework.routers import SimpleRouter

from .views import (
    HireReviewEligibilityView,
    ReviewViewSet,
    ServiceReviewListView,
)


router = SimpleRouter()

router.register(
    "",
    ReviewViewSet,
    basename="review",
)


urlpatterns = [
    path(
        "",
        include(router.urls),
    ),

    path(
        "services/<str:service_id>/",
        ServiceReviewListView.as_view(),
        name="service-review-list",
    ),

    path(
        "hires/<str:hire_id>/eligibility/",
        HireReviewEligibilityView.as_view(),
        name="hire-review-eligibility",
    ),
]