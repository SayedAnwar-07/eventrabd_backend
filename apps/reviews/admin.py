from django.contrib import admin
from django.utils.html import format_html
from .models import Review

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('event_brand_name', 'user_full_name', 'rating_stars', 'comment_preview', 'created_at')
    list_filter = ('rating', 'created_at', 'event__brand_name')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'event__brand_name', 'comment')
    readonly_fields = ('id', 'created_at', 'updated_at', 'user_full_name', 'event_brand_name')
    ordering = ('-created_at',)
    list_per_page = 20
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'user', 'event', 'rating')
        }),
        ('Review Content', {
            'fields': ('comment',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def event_brand_name(self, obj):
        return obj.event.brand_name
    event_brand_name.short_description = 'Event Brand'
    event_brand_name.admin_order_field = 'event__brand_name'
    
    def user_full_name(self, obj):
        return obj.user.get_full_name()
    user_full_name.short_description = 'User'
    user_full_name.admin_order_field = 'user__first_name'
    
    def rating_stars(self, obj):
        full_stars = int(obj.rating)
        half_star = obj.rating % 1 >= 0.5
        empty_stars = 5 - full_stars - (1 if half_star else 0)
        
        stars_html = ''
        stars_html += '★' * full_stars
        if half_star:
            stars_html += '½'
        stars_html += '☆' * empty_stars
        
        return format_html(
            '<span style="color: #ffa500; font-size: 16px;">{}</span> <span>({})</span>',
            stars_html, obj.rating
        )
    rating_stars.short_description = 'Rating'
    
    def comment_preview(self, obj):
        if obj.comment:
            preview = obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
            return format_html('<span title="{}">{}</span>', obj.comment, preview)
        return "-"
    comment_preview.short_description = 'Comment Preview'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('event', 'user')
    
    def changelist_view(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        
        total_reviews = Review.objects.count()
        avg_rating = Review.get_average_rating()
        
        extra_context['total_reviews'] = total_reviews
        extra_context['avg_rating'] = avg_rating
        
        return super().changelist_view(request, extra_context=extra_context)