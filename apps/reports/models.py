# models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.users.models import User
from apps.events.models import Event


def generate_report_id():
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    return get_random_string(10, allowed_chars=alphabet)


class ReportStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    UNDER_REVIEW = 'under_review', _('Under Review')
    RESOLVED = 'resolved', _('Resolved')
    REJECTED = 'rejected', _('Rejected')
    NEEDS_MORE_INFO = 'needs_more_info', _('Needs More Information')


class Report(models.Model):
    """
    A report submitted by any authenticated user against a specific Event.
    """
    id = models.CharField(
        primary_key=True,
        default=generate_report_id,
        editable=False,
        max_length=10
    )

    # Who is reporting?
    reporter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reports_made'
    )

    # What event is being reported?
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name='reports'
    )

    # Auto-filled from the event at creation:
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reports_received'
    )
    brand_name = models.CharField(max_length=100, db_index=True)
    seller_full_name = models.CharField(max_length=301)

    # Reporter-provided required fields:
    description = models.TextField(verbose_name=_('description'))
    user_full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)
    
    # Status management (admin only)
    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        db_index=True
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='status_changed_reports'
    )
    admin_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['brand_name']),
            models.Index(fields=['seller']),
            models.Index(fields=['event']),
            models.Index(fields=['reporter', 'event']),
            models.Index(fields=['status']),
        ]
        verbose_name = _('report')
        verbose_name_plural = _('reports')

    def clean(self):
        # Ensure seller always matches event.seller
        if self.event_id and self.seller_id and self.seller_id != self.event.seller_id:
            raise ValidationError(_("Seller must match the event's seller."))

    def save(self, *args, **kwargs):
        # Update status_changed_at when status changes
        if self.pk:
            try:
                original = Report.objects.get(pk=self.pk)
                if original.status != self.status:
                    self.status_changed_at = timezone.now()
            except Report.DoesNotExist:
                pass
        elif self.status != ReportStatus.PENDING:
            self.status_changed_at = timezone.now()
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Report {self.id} on {self.brand_name} (event {self.event_id}) by {self.reporter_id} - {self.status}"


class ReportImage(models.Model):
    """
    Up to 3 images (URL) per report.
    """
    MAX_IMAGES_PER_REPORT = 3

    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name='images'
    )
    image = models.URLField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
        indexes = [
            models.Index(fields=['report']),
        ]

    def clean(self):
        if not self.pk:
            current = ReportImage.objects.filter(report=self.report).count()
            if current >= self.MAX_IMAGES_PER_REPORT:
                raise ValidationError(
                    _(f"You can attach at most {self.MAX_IMAGES_PER_REPORT} images to a report.")
                )

    def __str__(self):
        return f"ReportImage({self.report_id})"