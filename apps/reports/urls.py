from django.urls import path
from . import views

urlpatterns = [
    path('<slug:event_slug>/reports/', views.EventReportsListCreateView.as_view(), name='event-reports'),
    path('<slug:user_slug>/reports/all/', views.UserReportsListView.as_view(), name='user-reports'),
    path('reports/<str:id>/', views.ReportDetailView.as_view(), name='report-detail'),
    path('reports/<str:id>/admin/', views.AdminReportUpdateView.as_view(), name='admin-report-update'),
]