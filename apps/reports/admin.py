from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Report, ReportImage, ReportStatus


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'brand_name', 'reporter', 'status', 'status_changed_at']
    list_filter = ['status', 'brand_name', 'created_at']
    search_fields = ['id', 'brand_name', 'reporter__email', 'reporter__username']
    readonly_fields = ['id', 'created_at', 'updated_at', 'status_changed_at']
    
    fieldsets = [
        (_('Basic Information'), {
            'fields': [
                'id',
                'status',
                'created_at',
                'updated_at',
                'status_changed_at',
                'status_changed_by'
            ]
        }),
        (_('Event Details'), {
            'fields': [
                'event',
                'brand_name',
                'seller',
                'seller_full_name'
            ]
        }),
        (_('Reporter Information'), {
            'fields': [
                'reporter',
                'user_full_name',
                'phone_number'
            ]
        }),
        (_('Report Content'), {
            'fields': [
                'description',
            ]
        }),
        (_('Admin Notes'), {
            'fields': [
                'admin_notes'
            ],
            'classes': ['collapse']
        }),
    ]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'reporter', 'seller', 'event', 'status_changed_by'
        )


@admin.register(ReportImage)
class ReportImageAdmin(admin.ModelAdmin):
    list_display = ['id', 'report', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['report__id', 'report__brand_name']
    readonly_fields = ['uploaded_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('report')