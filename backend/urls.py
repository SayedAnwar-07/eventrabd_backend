from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path("users/", include("apps.users.urls")),
    path("users/", include("apps.orders.urls")),
    path('events/', include('apps.events.urls')),
    path("events/", include("apps.reviews.urls")),
    path("events/", include("apps.reports.urls")),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
