from django.db import models
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft',   'Draft'),
        ('sent',    'Sent'),
        ('paid',    'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    # Reference
    invoice_no = models.CharField(max_length=30, unique=True, blank=True)
    quote_ref  = models.CharField(max_length=50, blank=True, help_text='Quotation reference number')

    # Optional FK to quotation
    quotation = models.ForeignKey(
        'quotations.Quotation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoices'
    )

    # Client
    client_name    = models.CharField(max_length=200)
    client_phone   = models.CharField(max_length=30, blank=True)
    client_email   = models.EmailField(blank=True)
    client_address = models.TextField(blank=True)

    # Dates
    invoice_date     = models.DateField(default=timezone.now)
    due_date         = models.DateField(blank=True, null=True)
    completion_date  = models.DateField(blank=True, null=True)

    # Work description
    description = models.TextField(
        default='Installation of windows and/or doors as per quotation reference above.'
    )

    # Financials
    contract_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    advance_paid    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    advance_payment_method = models.CharField(
        max_length=20,
        choices=[
            ('cash',          'Cash'),
            ('bank_transfer', 'Bank Transfer'),
            ('mobile_money',  'M-Pesa / Mobile Money'),
            ('cheque',        'Cheque'),
            ('unspecified',   'Unspecified'),
        ],
        default='unspecified',
        help_text='How was the advance payment received?',
    )

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes  = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.invoice_no} – {self.client_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            year = timezone.now().year
            last = Invoice.objects.filter(
                invoice_no__startswith=f'ADN-{year}-'
            ).order_by('-invoice_no').first()
            seq = 1
            if last:
                try:
                    seq = int(last.invoice_no.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            self.invoice_no = f'ADN-{year}-{seq:04d}'
        if not self.due_date:
            self.due_date = self.invoice_date + timedelta(days=30)
        super().save(*args, **kwargs)

    @property
    def total_paid(self):
        return self.advance_paid + sum(p.amount for p in self.payments.all())

    @property
    def balance_due(self):
        """Remaining balance. Returns 0 if overpaid (use overpaid_amount for excess)."""
        return max(self.contract_amount - self.total_paid, Decimal('0'))

    @property
    def overpaid_amount(self):
        """Positive value if client paid more than contract amount, else 0."""
        excess = self.total_paid - self.contract_amount
        return max(excess, Decimal('0'))

    @property
    def is_overdue(self):
        return (
            self.status not in ('paid', 'cancelled')
            and self.due_date
            and self.due_date < timezone.now().date()
        )


class InvoicePayment(models.Model):
    """Track individual payment installments."""
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money',  'Mobile Money (M-Pesa/Tigo Pesa)'),
        ('cash',          'Cash'),
        ('cheque',        'Cheque'),
    ]

    invoice        = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount         = models.DecimalField(max_digits=14, decimal_places=2)
    payment_date   = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default='bank_transfer')
    reference      = models.CharField(max_length=200, blank=True, help_text='Transaction ID / Cheque No.')
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment TZS {self.amount:,.0f} on {self.payment_date} for {self.invoice.invoice_no}"
