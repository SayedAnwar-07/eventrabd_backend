from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Review
from apps.events.models import Event
from .serializers import ReviewSerializer, ReviewCreateSerializer, ReviewUpdateSerializer
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

class ReviewListView(generics.ListAPIView):
    """
    Get all reviews for a specific event
    """
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        event_slug = self.kwargs['event_slug']
        event = get_object_or_404(Event, slug=event_slug)
        
        queryset = Review.objects.filter(event=event).select_related('user', 'event')
        
        # Filter by rating if provided
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            queryset = queryset.filter(rating__gte=float(min_rating))
        
        max_rating = self.request.query_params.get('max_rating')
        if max_rating:
            queryset = queryset.filter(rating__lte=float(max_rating))
        
        return queryset.order_by('-created_at')

class ReviewCreateView(generics.CreateAPIView):
    """
    Create a new review for a specific event
    """
    serializer_class = ReviewCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        event_slug = self.kwargs['event_slug']
        event = get_object_or_404(Event, slug=event_slug)
        
        # 1. Check if user is trying to review their own event (if seller)
        if self.request.user.user_type == 'seller' and event.seller == self.request.user:
            raise PermissionDenied({
                'detail': 'Sellers cannot review their own events.'
            })
        
        # 2. Check if user already reviewed this event
        if Review.objects.filter(user=self.request.user, event=event).exists():
            raise serializers.ValidationError({
                'event': 'You can only submit one review per event. Please edit your existing review instead.'
            })
        
        # 3. Check if user has reached the maximum limit of 5 reviews
        user_review_count = Review.objects.filter(user=self.request.user).count()
        if user_review_count >= 5:
            raise PermissionDenied({
                'detail': 'You have reached the maximum limit of 5 reviews.'
            })
        
        serializer.save(user=self.request.user, event=event)

class ReviewEditView(generics.UpdateAPIView):
    """
    Update an existing review (supports both PUT and PATCH)
    """
    serializer_class = ReviewUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        event_slug = self.kwargs['event_slug']
        event = get_object_or_404(Event, slug=event_slug)
        
        return Review.objects.filter(user=self.request.user, event=event)
    
    def perform_update(self, serializer):
        # Ensure the review belongs to the current user
        if serializer.instance.user != self.request.user:
            return Response(
                {'detail': 'You can only edit your own reviews.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer.save()

class ReviewDeleteView(generics.DestroyAPIView):
    """
    Delete a review
    """
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        event_slug = self.kwargs['event_slug']
        event = get_object_or_404(Event, slug=event_slug)
        
        # Users can only delete their own reviews for this event
        return Review.objects.filter(user=self.request.user, event=event)
    
    def perform_destroy(self, instance):
        # Double-check that the review belongs to the current user
        if instance.user != self.request.user:
            return Response(
                {'detail': 'You can only delete your own reviews.'},
                status=status.HTTP_403_FORBIDDEN
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)