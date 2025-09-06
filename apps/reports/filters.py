import django_filters
from apps.reports.models import Report, ReportStatus


class ReportFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=ReportStatus.choices)
    brand_name = django_filters.CharFilter(lookup_expr='icontains')
    seller_full_name = django_filters.CharFilter(lookup_expr='icontains')
    user_full_name = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    
    class Meta:
        model = Report
        fields = [
            'status', 
            'brand_name', 
            'seller', 
            'reporter', 
            'event',
            'seller_full_name',
            'user_full_name',
        ]