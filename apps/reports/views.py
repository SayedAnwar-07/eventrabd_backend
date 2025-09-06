from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied 
from django.shortcuts import get_object_or_404
from django.http import Http404
from apps.events.models import Event
from apps.reports.models import Report, ReportStatus
from apps.users.models import User
from apps.reports.serializers import ReportSerializer, AdminReportStatusUpdateSerializer


class EventReportsListCreateView(generics.ListCreateAPIView):
    """
    GET  /events/{slug}/reports/  → List reports for that event
    POST /events/{slug}/reports/  → Create a new report for that event
    """
    serializer_class = ReportSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            # Allow admin to see all reports, users to see only their own
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        event_slug = self.kwargs['event_slug']
        event = get_object_or_404(Event, slug=event_slug)
        
        queryset = Report.objects.filter(event=event).select_related(
            'reporter', 'seller', 'event', 'status_changed_by'
        ).prefetch_related('images')
        
        # Non-admin users can only see their own reports
        if not self.request.user.is_staff:
            queryset = queryset.filter(reporter=self.request.user)
            
        return queryset

    def perform_create(self, serializer):
        event_slug = self.kwargs['event_slug']
        event = get_object_or_404(Event, slug=event_slug)
        serializer.save(event=event)


class ReportDetailView(generics.RetrieveAPIView):
    """
    GET /reports/{report_id}/ → Get specific report details
    """
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        queryset = Report.objects.select_related(
            'reporter', 'seller', 'event', 'status_changed_by'
        ).prefetch_related('images')
        
        # Non-admin users can only see their own reports
        if not self.request.user.is_staff:
            queryset = queryset.filter(reporter=self.request.user)
            
        return queryset


class AdminReportUpdateView(generics.UpdateAPIView):
    """
    PATCH /reports/{report_id}/admin/ → Admin update report status
    """
    serializer_class = AdminReportStatusUpdateSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'id'
    queryset = Report.objects.all()
    
    
class UserReportsListView(generics.ListAPIView):

    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _get_user_by_profile_slug(self, user_slug: str) -> User:
        parts = [p for p in user_slug.split('-') if p]
        if not parts:
            raise Http404("User not found.")

        first_hint = parts[0]
        last_hint = parts[-1]

        candidates = User.objects.only('id', 'first_name', 'last_name').filter(
            first_name__istartswith=first_hint[:1], 
            last_name__istartswith=last_hint[:1]
        )

        if not candidates.exists():
            candidates = User.objects.only('id', 'first_name', 'last_name').all()

        for u in candidates:
            if u.get_profile_slug() == user_slug:
                return u

        raise Http404("User not found.")

    def get_queryset(self):
        user_slug = self.kwargs['user_slug']
        target_user = self._get_user_by_profile_slug(user_slug)

        request_user = self.request.user
        if not (request_user.is_staff or request_user.id == target_user.id):
            raise PermissionDenied("You cannot view another user's reports.")

        qs = (
            Report.objects
            .filter(reporter=target_user)
            .select_related('event', 'seller', 'status_changed_by')
            .prefetch_related('images')
            .order_by('-created_at')
        )

        status = self.request.query_params.get('status')
        valid_statuses = {choice[0] for choice in ReportStatus.choices}
        if status in valid_statuses:
            qs = qs.filter(status=status)

        return qs