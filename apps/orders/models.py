from decimal import Decimal
from django.db import models
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.core.validators import MinValueValidator
from apps.users.models import User
from apps.events.models import Event

def generate_order_id():
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    while True:
        new_id = get_random_string(8, allowed_chars=alphabet)
        if not ServiceOrder.objects.filter(pk=new_id).exists():
            return new_id

class ServiceOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'), 
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.CharField(
        primary_key=True,
        default=generate_order_id,
        max_length=8,
        editable=False
    )

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders_received')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders_made')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='orders')

    buyer_name = models.CharField(max_length=150)
    event_date = models.DateField()
    event_time = models.TimeField()
    location = models.CharField(max_length=255)
    selected_services = models.JSONField(default=list)

    seller_agreed = models.BooleanField(default=False)
    # buyer_agreed intentionally NOT added (not used in the simplified accept flow)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(0)]
    )

    # seller-provided fields
    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(0)]
    )

    advance_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(0)]
    )

    is_fully_paid = models.BooleanField(default=False)
    full_payment_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    invoice_file = models.URLField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['event_date']),
        ]

    def accept(self, by_seller=False):
        """
        Mark seller as agreed/accepted. This will set seller_agreed True and
        status to 'accepted'.
        """
        if by_seller:
            self.seller_agreed = True
            # move to accepted state
            self.status = 'accepted'
            self.save()

    def apply_seller_update(self, discount_price=None, advance_paid=None):
        """
        Apply seller-provided updates (discount_price and/or advance_paid),
        validate/cap them sensibly and recalculate payment status.
        """
        # defensive Decimal conversion
        if discount_price is None:
            discount_price = self.discount_price or Decimal('0.00')
        else:
            discount_price = Decimal(discount_price)

        if advance_paid is None:
            advance_paid = self.advance_paid or Decimal('0.00')
        else:
            advance_paid = Decimal(advance_paid)

        # Ensure discounts/advances are not negative
        if discount_price < 0:
            discount_price = Decimal('0.00')
        if advance_paid < 0:
            advance_paid = Decimal('0.00')

        # Cap discount to not exceed total_amount
        if discount_price > self.total_amount:
            discount_price = self.total_amount

        self.discount_price = discount_price
        self.advance_paid = advance_paid

        # Net total after discount
        net_total = (self.total_amount - self.discount_price)
        if net_total < 0:
            net_total = Decimal('0.00')

        # Fully paid check
        if self.advance_paid >= net_total and net_total > Decimal('0.00'):
            self.is_fully_paid = True
            if not self.full_payment_date:
                self.full_payment_date = timezone.now().date()
        elif net_total == Decimal('0.00'):
            self.is_fully_paid = True
            if not self.full_payment_date:
                self.full_payment_date = timezone.now().date()
        else:
            self.is_fully_paid = False

        self.save()

    @property
    def remaining_amount(self):
        """
        Remaining amount = total_amount - discount_price - advance_paid (never negative).
        """
        rem = (self.total_amount - (self.discount_price or Decimal('0.00')) - (self.advance_paid or Decimal('0.00')))
        return rem if rem > Decimal('0.00') else Decimal('0.00')

    def __str__(self):
        return f"Order {self.id} - {self.event.title} ({self.status})"
