from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('users/', include('apps.users.urls')),
    path('event-planner/', include('apps.event_planner.urls')),
    path('event-services/', include('apps.event_services.urls')),
    path('hire/', include('apps.hires.urls')),
    path('invoices/', include('apps.invoices.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('reviews/', include('apps.reviews.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)