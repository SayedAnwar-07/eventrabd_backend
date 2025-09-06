from django.urls import path
from . import views

urlpatterns = [
    path('<slug:event_slug>/reviews/', views.ReviewListView.as_view(), name='review-list'),
    path('<slug:event_slug>/reviews/create/', views.ReviewCreateView.as_view(), name='review-create'),
    path('<slug:event_slug>/reviews/<str:id>/edit/', views.ReviewEditView.as_view(), name='review-edit'),
    path('<slug:event_slug>/reviews/<str:id>/delete/', views.ReviewDeleteView.as_view(),  name='review-delete'),
]