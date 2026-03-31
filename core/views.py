from django.shortcuts import render
from django.db.models import Sum, Count, Q
from quotations.models import Quotation
from invoices.models import Invoice


def dashboard(request):
    # Quotation stats
    total_quotes = Quotation.objects.count()
    pending_quotes = Quotation.objects.filter(status='sent').count()
    accepted_quotes = Quotation.objects.filter(status='accepted').count()

    # Invoice stats
    total_invoices = Invoice.objects.count()
    unpaid_invoices = Invoice.objects.filter(status__in=['sent', 'overdue']).count()
    total_revenue = Invoice.objects.filter(status='paid').aggregate(
        total=Sum('contract_amount'))['total'] or 0

    recent_quotes = Quotation.objects.order_by('-created_at')[:5]
    recent_invoices = Invoice.objects.order_by('-created_at')[:5]

    context = {
        'total_quotes': total_quotes,
        'pending_quotes': pending_quotes,
        'accepted_quotes': accepted_quotes,
        'total_invoices': total_invoices,
        'unpaid_invoices': unpaid_invoices,
        'total_revenue': total_revenue,
        'recent_quotes': recent_quotes,
        'recent_invoices': recent_invoices,
    }
    return render(request, 'core/dashboard.html', context)
