from rest_framework.routers import SimpleRouter

from apps.hires.views import HireViewSet


router = SimpleRouter()

router.register(
    prefix="",
    viewset=HireViewSet,
    basename="hire",
)

urlpatterns = router.urls