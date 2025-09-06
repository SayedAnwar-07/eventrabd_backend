from django.urls import path
from .views import (
    CreateEvents,
    DetailsEvent,
    UpdateEvent,
    DeleteEvents,
    GlobalDashboardView,
    EventDashboardView,
    AllEventsView,
    SearchSuggestionsView,
)

urlpatterns = [
    path('', AllEventsView.as_view(), name='all-events'),
    path('suggestions/', SearchSuggestionsView.as_view(), name='search-suggestions'),
    path("create/", CreateEvents.as_view(), name="events-create"),
    path("<slug:slug>/", DetailsEvent.as_view(), name="events-detail"),
    path("<slug:slug>/update/", UpdateEvent.as_view(), name="events-update"),
    path("<slug:slug>/delete/", DeleteEvents.as_view(), name="events-delete"),
    
    # --- NEW Dashboard endpoints ---
    path("dashboard/", GlobalDashboardView.as_view(), name="events-dashboard-global"),
    path("<slug:slug>/dashboard/", EventDashboardView.as_view(), name="events-dashboard"),
]