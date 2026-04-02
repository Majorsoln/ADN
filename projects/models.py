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
        """Contract value: invoice if linked, else accepted quotation option."""
        if self.invoice_id:
            return self.invoice.contract_amount
        # Fall back to accepted quotation option value (before invoice is created)
        if self.quotation_id:
            q = self.quotation
            if q.accepted_material_id:
                for opt in q.material_options:
                    if opt['material'].pk == q.accepted_material_id:
                        return opt['grand']
        return Decimal('0')

    @property
    def revenue_source(self):
        """'invoice', 'quotation', or 'none' — for template labelling."""
        if self.invoice_id:
            return 'invoice'
        if self.quotation_id and self.quotation.accepted_material_id:
            return 'quotation'
        return 'none'

    @property
    def materials_cost(self):
        """Sum of all finalised material orders (not draft/cancelled)."""
        return sum(
            o.total_cost for o in self.orders.filter(
                status__in=['ordered', 'partially_received', 'received']
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

    # ── Status step index (for progress bar) ─────────────────────────────────

    STATUS_STEPS = ['planning', 'ordered', 'in_progress', 'completed']

    @property
    def status_step(self):
        try:
            return self.STATUS_STEPS.index(self.status)
        except ValueError:
            return 0

    @property
    def progress_pct(self):
        steps = len(self.STATUS_STEPS) - 1
        return int((self.status_step / steps) * 100)


class ProjectEvent(models.Model):
    """Immutable audit log for every meaningful project action."""

    TYPE_CHOICES = [
        ('created',      'Project Created'),
        ('status',       'Status Change'),
        ('order_new',    'Order Added'),
        ('order_status', 'Order Status Update'),
        ('order_edit',   'Order Edited'),
        ('order_del',    'Order Removed'),
        ('invoice',      'Invoice Linked'),
        ('note',         'Note'),
        ('completed',    'Project Completed'),
    ]

    ICON = {
        'created':      'bi-flag-fill text-primary',
        'status':       'bi-arrow-right-circle-fill text-warning',
        'order_new':    'bi-cart-plus-fill text-info',
        'order_status': 'bi-cart-check-fill text-success',
        'order_edit':   'bi-pencil-fill text-secondary',
        'order_del':    'bi-trash-fill text-danger',
        'invoice':      'bi-receipt-cutoff text-success',
        'note':         'bi-chat-left-text-fill text-muted',
        'completed':    'bi-check-circle-fill text-success',
    }

    project     = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='events')
    event_type  = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.TextField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.event_type}] {self.project.name}"

    @property
    def icon_class(self):
        return self.ICON.get(self.event_type, 'bi-circle-fill text-muted')
