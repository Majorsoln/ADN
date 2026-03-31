from django.db import models
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


class Material(models.Model):
    """Reusable material price list (global defaults)."""
    name = models.CharField(max_length=200)
    price_per_sqm = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} – TZS {self.price_per_sqm:,.0f}/m²"


class Quotation(models.Model):
    STATUS_CHOICES = [
        ('draft',    'Draft'),
        ('sent',     'Sent to Client'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired',  'Expired'),
    ]
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage (%)'),
        ('fixed',      'Fixed Amount (TZS)'),
    ]

    # Reference
    quote_no = models.CharField(max_length=30, unique=True, blank=True)

    # Client info
    client_name    = models.CharField(max_length=200)
    client_phone   = models.CharField(max_length=30, blank=True)
    client_email   = models.EmailField(blank=True)
    client_address = models.TextField(blank=True)

    # Project
    project_name       = models.CharField(max_length=300, blank=True)
    installation_days  = models.PositiveIntegerField(default=7, help_text='Working days')
    notes              = models.TextField(blank=True)

    # Dates
    quote_date  = models.DateField(default=timezone.now)
    valid_until = models.DateField(blank=True, null=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Discount
    discount_name     = models.CharField(max_length=100, blank=True)
    discount_duration = models.CharField(max_length=100, blank=True)
    discount_type     = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    discount_value    = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Taxes
    vat_enabled      = models.BooleanField(default=False)
    vat_rate         = models.DecimalField(max_digits=5, decimal_places=2, default=18)

    service_levy_enabled = models.BooleanField(default=False)
    service_levy_rate    = models.DecimalField(max_digits=5, decimal_places=2, default=0.3)

    skills_levy_enabled = models.BooleanField(default=False)
    skills_levy_rate    = models.DecimalField(max_digits=5, decimal_places=2, default=0.3)

    withholding_enabled = models.BooleanField(default=False)
    withholding_rate    = models.DecimalField(max_digits=5, decimal_places=2, default=5)

    custom1_name    = models.CharField(max_length=100, blank=True)
    custom1_rate    = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    custom1_enabled = models.BooleanField(default=False)

    custom2_name    = models.CharField(max_length=100, blank=True)
    custom2_rate    = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    custom2_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.quote_no} – {self.client_name}"

    def save(self, *args, **kwargs):
        if not self.quote_no:
            year = timezone.now().year
            last = Quotation.objects.filter(
                quote_no__startswith=f'QT-{year}-'
            ).order_by('-quote_no').first()
            seq = 1
            if last:
                try:
                    seq = int(last.quote_no.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            self.quote_no = f'QT-{year}-{seq:04d}'
        if not self.valid_until:
            self.valid_until = self.quote_date + timedelta(days=30)
        super().save(*args, **kwargs)

    # ── Computed totals ──────────────────────────────────────────────────────

    @property
    def total_area(self):
        """Total area in m²."""
        return sum(item.area for item in self.items.all())

    @property
    def material_options(self):
        """Returns list of dicts with per-material calculations."""
        results = []
        for qm in self.quote_materials.all():
            subtotal   = qm.price_per_sqm * Decimal(str(self.total_area))
            discount   = self._calc_discount(subtotal)
            after_disc = subtotal - discount
            taxes      = self._calc_taxes(after_disc)
            tax_total  = sum(t['amount'] for t in taxes)
            grand      = after_disc + tax_total
            results.append({
                'material':   qm,
                'subtotal':   subtotal,
                'discount':   discount,
                'after_disc': after_disc,
                'taxes':      taxes,
                'tax_total':  tax_total,
                'grand':      grand,
            })
        return results

    def _calc_discount(self, subtotal):
        if self.discount_value == 0:
            return Decimal('0')
        if self.discount_type == 'percentage':
            return subtotal * (self.discount_value / 100)
        return min(self.discount_value, subtotal)

    def _calc_taxes(self, base):
        taxes = []
        if self.vat_enabled:
            taxes.append({'name': f'VAT ({self.vat_rate}%)',
                          'rate': self.vat_rate,
                          'amount': base * (self.vat_rate / 100)})
        if self.service_levy_enabled:
            taxes.append({'name': f'Service Levy ({self.service_levy_rate}%)',
                          'rate': self.service_levy_rate,
                          'amount': base * (self.service_levy_rate / 100)})
        if self.skills_levy_enabled:
            taxes.append({'name': f'Skills & Development Levy ({self.skills_levy_rate}%)',
                          'rate': self.skills_levy_rate,
                          'amount': base * (self.skills_levy_rate / 100)})
        if self.withholding_enabled:
            taxes.append({'name': f'Withholding Tax ({self.withholding_rate}%)',
                          'rate': self.withholding_rate,
                          'amount': base * (self.withholding_rate / 100)})
        if self.custom1_enabled and self.custom1_name:
            taxes.append({'name': f'{self.custom1_name} ({self.custom1_rate}%)',
                          'rate': self.custom1_rate,
                          'amount': base * (self.custom1_rate / 100)})
        if self.custom2_enabled and self.custom2_name:
            taxes.append({'name': f'{self.custom2_name} ({self.custom2_rate}%)',
                          'rate': self.custom2_rate,
                          'amount': base * (self.custom2_rate / 100)})
        return taxes


class QuotationItem(models.Model):
    """A window or door line-item in the quotation."""
    quotation   = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items')
    item_type   = models.CharField(max_length=200, help_text='e.g. Casement Window, Sliding Door')
    description = models.TextField(blank=True)
    width       = models.DecimalField(max_digits=8, decimal_places=2, help_text='Width in cm')
    height      = models.DecimalField(max_digits=8, decimal_places=2, help_text='Height in cm')
    quantity    = models.PositiveIntegerField(default=1)
    order       = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.item_type} {self.width}×{self.height}cm ×{self.quantity}"

    @property
    def area(self):
        """Area in m²."""
        return (self.width * self.height * self.quantity) / Decimal('10000')

    @property
    def area_display(self):
        return round(self.area, 4)


class QuotationMaterial(models.Model):
    """A material option attached to a specific quotation (editable price snapshot)."""
    quotation     = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='quote_materials')
    material_name = models.CharField(max_length=200)
    price_per_sqm = models.DecimalField(max_digits=12, decimal_places=2)
    notes         = models.CharField(max_length=300, blank=True)
    order         = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.material_name} @ TZS {self.price_per_sqm:,.0f}/m²"
