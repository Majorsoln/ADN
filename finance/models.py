from django.db import models
from django.utils import timezone
from decimal import Decimal


class ExpenseCategory(models.Model):
    """Classifies business expenses (Salaries, Rent, Utilities, etc.)"""
    name       = models.CharField(max_length=100, unique=True)
    icon       = models.CharField(max_length=60, default='bi-tag', blank=True)
    color      = models.CharField(max_length=20, default='#64748b', blank=True)
    is_active  = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'Expense Categories'

    def __str__(self):
        return self.name

    @classmethod
    def create_defaults(cls):
        """Seed standard categories on first run."""
        defaults = [
            ('Salaries & Wages',     'bi-people-fill',      '#2563eb', 1),
            ('Rent & Premises',      'bi-building',         '#7c3aed', 2),
            ('Utilities',            'bi-lightning-fill',   '#d97706', 3),
            ('Transport & Fuel',     'bi-truck',            '#0891b2', 4),
            ('Office Supplies',      'bi-printer-fill',     '#64748b', 5),
            ('Project Materials',    'bi-box-seam-fill',    '#b45309', 6),
            ('Repairs & Maintenance','bi-tools',            '#16a34a', 7),
            ('Marketing',            'bi-megaphone-fill',   '#db2777', 8),
            ('Professional Fees',    'bi-briefcase-fill',   '#4f46e5', 9),
            ('Petty Cash',           'bi-cash-coin',        '#059669', 10),
            ('Other Expenses',       'bi-three-dots',       '#94a3b8', 99),
        ]
        for name, icon, color, order in defaults:
            cls.objects.get_or_create(name=name, defaults={
                'icon': icon, 'color': color, 'sort_order': order
            })


class Expense(models.Model):
    """Records every money-out transaction for the business."""
    PAYMENT_CHOICES = [
        ('cash',   'Cash'),
        ('bank',   'Bank Transfer'),
        ('mpesa',  'M-Pesa / Mobile Money'),
        ('cheque', 'Cheque'),
        ('other',  'Other'),
    ]

    category       = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT,
                                       related_name='expenses')
    amount         = models.DecimalField(max_digits=14, decimal_places=2)
    date           = models.DateField(default=timezone.now)
    description    = models.TextField()
    paid_to        = models.CharField(max_length=200, blank=True,
                                      help_text='Vendor / payee name')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='cash')
    reference      = models.CharField(max_length=100, blank=True,
                                      help_text='Receipt or transaction number')
    project        = models.ForeignKey('projects.Project', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='expenses',
                                       help_text='Link if this is a project expense')
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.category.name} – TZS {self.amount:,.0f} ({self.date})"


class ReportSnapshot(models.Model):
    """Archived financial report — stores computed figures for future reference."""
    REPORT_TYPES = [
        ('snapshot', 'Daily Snapshot'),
        ('weekly',   'Weekly Report'),
        ('monthly',  'Monthly Report'),
        ('custom',   'Custom Period Report'),
    ]

    report_type  = models.CharField(max_length=20, choices=REPORT_TYPES, default='monthly')
    title        = models.CharField(max_length=200)
    period_from  = models.DateField()
    period_to    = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    figures      = models.JSONField(default=dict,
                                    help_text='Computed financial figures as JSON')
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['-generated_at']
        verbose_name = 'Report Snapshot'

    def __str__(self):
        return f"{self.title} ({self.period_from} – {self.period_to})"

    @property
    def total_income(self):
        return Decimal(str(self.figures.get('total_income', 0)))

    @property
    def total_expenses(self):
        return Decimal(str(self.figures.get('total_expenses', 0)))

    @property
    def net_profit(self):
        return Decimal(str(self.figures.get('net_profit', 0)))
