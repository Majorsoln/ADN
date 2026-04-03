from django.db import models
from django.contrib.auth.models import User
from projects.models import Project


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    client_name = models.CharField(max_length=255)
    client_phone = models.CharField(max_length=50, blank=True)
    client_address = models.TextField(blank=True)
    description = models.TextField(blank=True)
    quotation_ref = models.CharField(max_length=100, blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    advance_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def balance_due(self):
        return self.total_amount - self.advance_paid

    def __str__(self):
        return f"INV-{self.invoice_number}"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.description


class Quote(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='quotes', null=True, blank=True)
    quote_number = models.CharField(max_length=50, unique=True)
    client_name = models.CharField(max_length=255)
    project_name = models.CharField(max_length=255)
    installation_days = models.IntegerField(default=14)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_name = models.CharField(max_length=255, blank=True)
    discount_type = models.CharField(max_length=20, default='percentage', choices=[('percentage', 'Percentage'), ('flat', 'Flat Amount')])
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_enabled = models.BooleanField(default=False)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    service_levy_enabled = models.BooleanField(default=False)
    service_levy_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2)
    notes = models.TextField(blank=True)
    valid_until = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"QT-{self.quote_number}"


class QuoteItem(models.Model):
    ITEM_TYPE_CHOICES = [
        ('window', 'Window'),
        ('door', 'Door'),
        ('fixed', 'Fixed'),
        ('fixed_door', 'Fixed with Door'),
        ('fixed_sliding', 'Fixed with Sliding Door'),
        ('fixed_window', 'Fixed with Window'),
    ]

    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=500)
    width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    material = models.CharField(max_length=100, blank=True)
    item_type = models.CharField(max_length=100, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def area_sqm(self):
        if self.width and self.height:
            return (self.width * self.height * self.quantity) / 10000
        return 0

    @property
    def total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.description


class ProjectReport(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reports')
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    report_date = models.DateField(auto_now_add=True)
    prepared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    pdf_file = models.FileField(upload_to='reports/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Report: {self.title}"
