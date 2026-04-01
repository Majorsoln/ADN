from django.shortcuts import render
from django.db.models import Sum, Count
from django.utils import timezone
from quotations.models import Quotation
from invoices.models import Invoice
from projects.models import Project
from office.models import OfficeServiceRecord, OfficeIncome


def dashboard(request):
    today = timezone.now().date()

    # Quotation stats
    total_quotes    = Quotation.objects.count()
    pending_quotes  = Quotation.objects.filter(status='sent').count()
    accepted_quotes = Quotation.objects.filter(status='accepted').count()

    # Invoice stats
    total_invoices  = Invoice.objects.count()
    unpaid_invoices = Invoice.objects.filter(status__in=['sent', 'overdue']).count()
    total_revenue   = Invoice.objects.filter(status='paid').aggregate(t=Sum('contract_amount'))['t'] or 0

    # Project stats
    active_projects    = Project.objects.filter(status__in=['planning', 'ordered', 'in_progress']).count()
    completed_projects = Project.objects.filter(status='completed').count()

    # Office service stats
    pending_debts = OfficeServiceRecord.objects.filter(status__in=['pending', 'partial'])
    total_debt    = sum(r.balance for r in pending_debts)

    # Income from DB
    income_qs       = OfficeIncome.objects.all()
    project_profit  = income_qs.filter(source='project_profit').aggregate(t=Sum('amount'))['t'] or 0
    service_income  = income_qs.filter(source='office_service').aggregate(t=Sum('amount'))['t'] or 0
    other_income    = income_qs.filter(source='other').aggregate(t=Sum('amount'))['t'] or 0
    total_income    = project_profit + service_income + other_income

    recent_quotes   = Quotation.objects.order_by('-created_at')[:5]
    recent_invoices = Invoice.objects.order_by('-created_at')[:5]
    recent_projects = Project.objects.order_by('-created_at')[:5]
    recent_debts    = OfficeServiceRecord.objects.filter(status__in=['pending', 'partial']).order_by('-date_recorded')[:5]

    context = {
        'total_quotes':    total_quotes,
        'pending_quotes':  pending_quotes,
        'accepted_quotes': accepted_quotes,
        'total_invoices':  total_invoices,
        'unpaid_invoices': unpaid_invoices,
        'total_revenue':   total_revenue,
        'active_projects':    active_projects,
        'completed_projects': completed_projects,
        'total_debt':      total_debt,
        'project_profit':  project_profit,
        'service_income':  service_income,
        'other_income':    other_income,
        'total_income':    total_income,
        'recent_quotes':   recent_quotes,
        'recent_invoices': recent_invoices,
        'recent_projects': recent_projects,
        'recent_debts':    recent_debts,
    }
    return render(request, 'core/dashboard.html', context)
