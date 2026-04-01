from django.db import models
from django.utils import timezone
from decimal import Decimal


class MaterialOrder(models.Model):
    STATUS_CHOICES = [
        ('draft',               'Draft'),
        ('ordered',             'Ordered'),
        ('partially_received',  'Partially Received'),
        ('received',            'Received'),
        ('cancelled',           'Cancelled'),
    ]
    PAYMENT_SOURCE_CHOICES = [
        ('cash',        'Cash'),
        ('bank',        'Bank Transfer'),
        ('mpesa',       'M-Pesa / Mobile Money'),
        ('cheque',      'Cheque'),
        ('unspecified', 'Not specified'),
    ]

    project           = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='orders')
    supplier_name     = models.CharField(max_length=200)
    order_date        = models.DateField(default=timezone.now)
    expected_delivery = models.DateField(null=True, blank=True)
    actual_delivery   = models.DateField(null=True, blank=True)
    status            = models.CharField(max_length=25, choices=STATUS_CHOICES, default='draft')
    payment_source    = models.CharField(max_length=15, choices=PAYMENT_SOURCE_CHOICES,
                                         default='unspecified',
                                         help_text='Where did the money come from to pay for this order?')
    notes             = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date', '-created_at']

    def __str__(self):
        return f"Order from {self.supplier_name} – {self.project.name}"

    @property
    def total_cost(self):
        return sum(item.total for item in self.items.all())

    @property
    def is_overdue(self):
        return (
            self.expected_delivery
            and self.status not in ('received', 'cancelled')
            and self.expected_delivery < timezone.now().date()
        )

    # Steps: draft=0, ordered=1, partially_received=2, received=3
    STATUS_STEPS = ['draft', 'ordered', 'partially_received', 'received']

    @property
    def status_step(self):
        try:
            return self.STATUS_STEPS.index(self.status)
        except ValueError:
            return 0


class MaterialOrderItem(models.Model):
    UNIT_CHOICES = [
        ('m2',  'm² (Square Meters)'),
        ('pcs', 'Pcs (Pieces)'),
        ('kg',  'Kg (Kilograms)'),
        ('m',   'm (Meters)'),
        ('set', 'Set'),
        ('box', 'Box'),
    ]

    order         = models.ForeignKey(MaterialOrder, on_delete=models.CASCADE, related_name='items')
    material_name = models.CharField(max_length=200)
    description   = models.CharField(max_length=300, blank=True)
    quantity      = models.DecimalField(max_digits=10, decimal_places=3)
    unit          = models.CharField(max_length=10, choices=UNIT_CHOICES, default='m2')
    unit_cost     = models.DecimalField(max_digits=12, decimal_places=2)
    order_index   = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order_index', 'id']

    def __str__(self):
        return f"{self.material_name} x{self.quantity} {self.unit}"

    @property
    def total(self):
        return self.quantity * self.unit_cost
