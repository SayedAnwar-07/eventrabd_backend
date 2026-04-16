from django.contrib import admin
from .models import EventBrand
 
@admin.register(EventBrand)
class EventBrandAdmin(admin.ModelAdmin):
    list_display  = ["brand_name", "seller", "service_area", "created_at"]
    list_filter   = ["service_area"]
    search_fields = ["brand_name", "seller__email", "seller__full_name"]
    readonly_fields = ["slug", "id", "created_at", "updated_at"]