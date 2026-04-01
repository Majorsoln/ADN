from django.db import models
from django.utils import timezone
from decimal import Decimal


class Project(models.Model):
    STATUS_CHOICES = [
        ('planning',    'Planning'),
        ('ordered',     'Materials Ordered'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
        ('cancelled',   'Cancelled'),
    ]

    # Link to quotation and invoice
    quotation = models.OneToOneField(
        'quotations.Quotation', on_delete=models.PROTECT,
        related_name='project', null=True, blank=True
    )
    invoice = models.ForeignKey(
        'invoices.Invoice', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='projects'
    )

    # Basic info (copied from quotation or manual)
    name         = models.CharField(max_length=300)
    client_name  = models.CharField(max_length=200)
    client_phone = models.CharField(max_length=30, blank=True)
    description  = models.TextField(blank=True)

    # Status & dates
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    start_date      = models.DateField(default=timezone.now)
    target_date     = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    notes           = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} – {self.client_name}"

    # ── Financial properties ─────────────────────────────────────────────────

    @property
    def revenue(self):
        """What the client paid (from linked invoice)."""
        if self.invoice:
            return self.invoice.contract_amount
        return Decimal('0')

    @property
    def materials_cost(self):
        """Sum of all received/completed material orders."""
        return sum(
            o.total_cost for o in self.orders.filter(
                status__in=['received', 'ordered', 'partially_received']
            )
        )

    @property
    def gross_profit(self):
        return self.revenue - self.materials_cost

    @property
    def profit_margin(self):
        if self.revenue > 0:
            return (self.gross_profit / self.revenue) * 100
        return Decimal('0')

    @property
    def days_elapsed(self):
        end = self.completion_date or timezone.now().date()
        return (end - self.start_date).days if self.start_date else 0
