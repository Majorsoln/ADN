from django.db import models
from django.utils import timezone
from decimal import Decimal


class OfficeServiceRate(models.Model):
    """Active pricing rate for office service charges."""
    rate_per_window = models.DecimalField(max_digits=10, decimal_places=2, help_text='TZS per window')
    rate_per_door   = models.DecimalField(max_digits=10, decimal_places=2, help_text='TZS per door')
    effective_from  = models.DateField(default=timezone.now)
    notes           = models.CharField(max_length=200, blank=True)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_from']

    def __str__(self):
        return f"Rate: TZS {self.rate_per_window}/window · TZS {self.rate_per_door}/door (from {self.effective_from})"

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()


class OfficeServiceRecord(models.Model):
    """Someone using the office for their window/door job — tracked until fully paid."""
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('partial', 'Partially Paid'),
        ('paid',    'Fully Paid'),
    ]

    # Who
    client_name    = models.CharField(max_length=200)
    client_phone   = models.CharField(max_length=30, blank=True)
    client_address = models.TextField(blank=True)

    # What work
    work_description = models.TextField(blank=True, help_text='Describe the windows/doors work')
    num_windows      = models.PositiveIntegerField(default=0)
    num_doors        = models.PositiveIntegerField(default=0)

    # Pricing (snapshot at time of record)
    rate_per_window = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rate_per_door   = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Dates
    date_recorded = models.DateField(default=timezone.now)
    due_date      = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    notes  = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_recorded']

    def __str__(self):
        return f"{self.client_name} – {self.num_windows}W/{self.num_doors}D – {self.status}"

    @property
    def total_charge(self):
        return (
            Decimal(str(self.num_windows)) * self.rate_per_window
            + Decimal(str(self.num_doors)) * self.rate_per_door
        )

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments.all())

    @property
    def balance(self):
        return self.total_charge - self.total_paid

    @property
    def is_overdue(self):
        return (
            self.status != 'paid'
            and self.due_date
            and self.due_date < timezone.now().date()
        )


class OfficeServicePayment(models.Model):
    METHOD_CHOICES = [
        ('cash',          'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money',  'Mobile Money'),
        ('cheque',        'Cheque'),
    ]

    record         = models.ForeignKey(OfficeServiceRecord, on_delete=models.CASCADE, related_name='payments')
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date   = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash')
    reference      = models.CharField(max_length=200, blank=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment TZS {self.amount:,.0f} – {self.record.client_name}"


class OfficeIncome(models.Model):
    """Consolidated income record: from projects profit + office service payments."""
    SOURCE_CHOICES = [
        ('project_profit',  'Project Profit'),
        ('office_service',  'Office Service Charge'),
        ('other',           'Other'),
    ]

    source       = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    amount       = models.DecimalField(max_digits=14, decimal_places=2)
    date         = models.DateField(default=timezone.now)
    description  = models.TextField(blank=True)
    # Optional links
    project      = models.ForeignKey('projects.Project', on_delete=models.SET_NULL, null=True, blank=True)
    office_record = models.ForeignKey(OfficeServiceRecord, on_delete=models.SET_NULL, null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.get_source_display()} – TZS {self.amount:,.0f} ({self.date})"
