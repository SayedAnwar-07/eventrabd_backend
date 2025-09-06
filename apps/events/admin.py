# apps/events/admin.py
from django.contrib import admin
from .models import Event, EventService, EventServiceDetail, EventGallery


class EventServiceDetailInline(admin.TabularInline):
    model = EventServiceDetail
    extra = 1
    autocomplete_fields = ['service']


class EventGalleryInline(admin.TabularInline):
    model = EventGallery
    extra = 1
    fields = ['image', 'position', 'is_primary']
    readonly_fields = ['uploaded_at']
    ordering = ['position']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['brand_name', 'title', 'seller', 'slug', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at', 'seller']
    search_fields = ['brand_name', 'title', 'slug', 'seller__username', 'seller__email']
    readonly_fields = ['id', 'slug', 'created_at', 'updated_at',
                       'total_views', 'total_reviews', 'average_rating']
    inlines = [EventServiceDetailInline, EventGalleryInline]
    ordering = ['-created_at']


@admin.register(EventService)
class EventServiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'service_type', 'created_at']
    search_fields = ['id', 'service_type']
    ordering = ['service_type']


@admin.register(EventServiceDetail)
class EventServiceDetailAdmin(admin.ModelAdmin):
    list_display = ['event', 'service', 'short_description', 'price', 'is_available', 'created_at']
    list_filter = ['is_available', 'created_at']
    search_fields = ['event__title', 'event__brand_name', 'service__service_type']
    autocomplete_fields = ['event', 'service']


@admin.register(EventGallery)
class EventGalleryAdmin(admin.ModelAdmin):
    list_display = ['event', 'position', 'is_primary', 'image', 'uploaded_at']
    list_filter = ['is_primary', 'uploaded_at']
    search_fields = ['event__title', 'event__brand_name']
    autocomplete_fields = ['event']
    ordering = ['event', 'position']
