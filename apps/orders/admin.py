from django.contrib import admin
from django.utils.html import format_html
from .models import ServiceOrder

@admin.register(ServiceOrder)
class ServiceOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'event_logo', 'event', 'seller', 'buyer', 'status',
        'event_date', 'event_time', 'total_amount', 'advance_paid', 'created_at'
    )
    list_filter = ('status', 'seller', 'buyer', 'event_date')
    search_fields = (
        'id', 'event__title', 'seller__first_name', 'seller__last_name',
        'buyer__first_name', 'buyer__last_name', 'location'
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)

    def event_logo(self, obj):
        """Display event logo as image in admin list"""
        if obj.event.logo:
            return format_html(
                '<img src="{}" style="width:50px; height:auto; border-radius:4px;" />', 
                obj.event.logo
            )
        return "-"
    event_logo.short_description = 'Event Logo'
