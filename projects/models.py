from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class Project(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('in_progress', 'In Progress'),
        ('review', 'Under Review'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
        ('on_hold', 'On Hold'),
    ]
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    client_name = models.CharField(max_length=255)
    client_phone = models.CharField(max_length=50, blank=True)
    client_email = models.EmailField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    budget = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    completion_percentage = models.IntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} - {self.client_name}"

    @property
    def total_material_cost(self):
        return self.materials.aggregate(
            total=models.Sum(models.F('quantity') * models.F('unit_price'))
        )['total'] or Decimal('0')

    @property
    def total_labor_cost(self):
        return self.labor_costs.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def total_transport_cost(self):
        return self.transport_costs.aggregate(total=models.Sum('cost'))['total'] or Decimal('0')

    @property
    def total_other_expenses(self):
        return self.other_expenses.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def total_expenses(self):
        return self.total_material_cost + self.total_labor_cost + self.total_transport_cost + self.total_other_expenses

    @property
    def total_revenue(self):
        return self.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def total_invoiced(self):
        return self.invoices.aggregate(total=models.Sum('total_amount'))['total'] or Decimal('0')

    @property
    def profit_loss(self):
        return self.total_revenue - self.total_expenses

    @property
    def profit_margin(self):
        if self.total_revenue > 0:
            return (self.profit_loss / self.total_revenue) * 100
        return Decimal('0')

    @property
    def is_overdue(self):
        if self.end_date and self.status not in ('completed', 'archived'):
            return timezone.now().date() > self.end_date
        return False

    @property
    def days_remaining(self):
        if self.end_date:
            delta = self.end_date - timezone.now().date()
            return delta.days
        return None


class TeamMember(models.Model):
    ROLE_CHOICES = [
        ('manager', 'Project Manager'),
        ('engineer', 'Engineer'),
        ('technician', 'Technician'),
        ('installer', 'Installer'),
        ('designer', 'Designer'),
        ('accountant', 'Accountant'),
        ('other', 'Other'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='team_members')
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='technician')
    phone = models.CharField(max_length=50, blank=True)
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_date = models.DateField(null=True, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title


class Material(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='materials')
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=50, default='pcs')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    date_added = models.DateField(default=timezone.now)

    @property
    def total_cost(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"


class LaborCost(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='labor_costs')
    description = models.CharField(max_length=500)
    worker_name = models.CharField(max_length=255, blank=True)
    days = models.DecimalField(max_digits=6, decimal_places=1, default=1)
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)

    def __str__(self):
        return self.description


class TransportCost(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='transport_costs')
    vehicle_type = models.CharField(max_length=100)
    from_location = models.CharField(max_length=255)
    to_location = models.CharField(max_length=255)
    cost = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.from_location} → {self.to_location}"


class OtherExpense(models.Model):
    CATEGORY_CHOICES = [
        ('permits', 'Permits & Licenses'),
        ('insurance', 'Insurance'),
        ('utilities', 'Utilities'),
        ('tools', 'Tools & Equipment'),
        ('miscellaneous', 'Miscellaneous'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='other_expenses')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='miscellaneous')
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.get_category_display()}: {self.description}"


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money (M-Pesa/Tigo Pesa)'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash')
    reference = models.CharField(max_length=255, blank=True)
    date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"TZS {self.amount:,.2f} - {self.get_method_display()}"


class ActivityLog(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=500)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} - {self.timestamp}"


class Task(models.Model):
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(TeamMember, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='todo')
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['status', '-created_at']

    def __str__(self):
        return self.title
