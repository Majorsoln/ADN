from datetime import date, timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.utils import timezone

from .engine import compute_snapshot, compute_report
from .forms import ExpenseForm, ReportFilterForm, SaveReportForm
from .models import Expense, ExpenseCategory, ReportSnapshot


# ── Level-1 Owner Snapshot ────────────────────────────────────────────────────

def snapshot_view(request):
    """Daily money-in / money-out / balance view for the owner."""
    raw_date = request.GET.get('date')
    try:
        for_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        for_date = date.today()

    data = compute_snapshot(for_date=for_date)
    return render(request, 'finance/snapshot.html', {
        'data': data,
        'for_date': for_date,
        'prev_date': for_date - timedelta(days=1),
        'next_date': for_date + timedelta(days=1),
        'is_today': for_date == date.today(),
    })


# ── Level-2/3 Business / Accounting Report ────────────────────────────────────

def report_view(request):
    """Full period report: income breakdown, expenses, receivables, project stats."""
    form = ReportFilterForm(request.GET or None)
    data = None
    date_from = date_to = None

    if request.GET and form.is_valid():
        date_from, date_to = form.resolve_period()
        data = compute_report(date_from, date_to)
    elif not request.GET:
        # Default: this month
        today = date.today()
        date_from = date(today.year, today.month, 1)
        date_to = today
        form = ReportFilterForm(initial={'period': 'this_month'})
        data = compute_report(date_from, date_to)

    return render(request, 'finance/report.html', {
        'form': form,
        'data': data,
        'date_from': date_from,
        'date_to': date_to,
    })


def report_pdf_view(request):
    """Render the current report as a print-ready PDF page."""
    form = ReportFilterForm(request.GET or None)
    date_from = date_to = None
    data = None

    if form.is_valid():
        date_from, date_to = form.resolve_period()
    else:
        today = date.today()
        date_from = date(today.year, today.month, 1)
        date_to = today

    data = compute_report(date_from, date_to)
    return render(request, 'finance/report_pdf.html', {
        'data': data,
        'date_from': date_from,
        'date_to': date_to,
        'generated_at': timezone.now(),
    })


def save_report_view(request):
    """Save computed report figures as a ReportSnapshot for future reference."""
    if request.method == 'POST':
        form = SaveReportForm(request.POST)
        if form.is_valid():
            snapshot = form.save(commit=False)
            # Re-compute figures for the saved period
            snapshot.figures = compute_report(snapshot.period_from, snapshot.period_to)
            snapshot.save()
            messages.success(request, f'Report "{snapshot.title}" saved successfully.')
            return redirect('finance:archive')
    else:
        # Pre-fill from GET params
        today = date.today()
        form = SaveReportForm(initial={
            'period_from': request.GET.get('date_from', date(today.year, today.month, 1)),
            'period_to': request.GET.get('date_to', today),
            'report_type': request.GET.get('report_type', 'monthly'),
            'title': request.GET.get('title', ''),
        })

    return render(request, 'finance/save_report.html', {'form': form})


# ── Archive ───────────────────────────────────────────────────────────────────

def archive_view(request):
    """List of saved report snapshots."""
    snapshots = ReportSnapshot.objects.all()
    report_type = request.GET.get('type', '')
    if report_type:
        snapshots = snapshots.filter(report_type=report_type)

    return render(request, 'finance/archive.html', {
        'snapshots': snapshots,
        'report_type': report_type,
        'report_types': ReportSnapshot.REPORT_TYPES,
    })


def archive_detail_view(request, pk):
    """View a saved report snapshot."""
    snapshot = get_object_or_404(ReportSnapshot, pk=pk)
    return render(request, 'finance/archive_detail.html', {
        'snapshot': snapshot,
        'data': snapshot.figures,
    })


def archive_delete_view(request, pk):
    snapshot = get_object_or_404(ReportSnapshot, pk=pk)
    if request.method == 'POST':
        title = snapshot.title
        snapshot.delete()
        messages.success(request, f'Report "{title}" deleted.')
        return redirect('finance:archive')
    return render(request, 'finance/archive_confirm_delete.html', {'snapshot': snapshot})


# ── Expenses CRUD ─────────────────────────────────────────────────────────────

def expense_list_view(request):
    expenses = Expense.objects.select_related('category', 'project').all()

    # Filter
    category_id = request.GET.get('category')
    if category_id:
        expenses = expenses.filter(category_id=category_id)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        expenses = expenses.filter(date__lte=date_to)

    categories = ExpenseCategory.objects.filter(is_active=True)
    total = sum(e.amount for e in expenses)

    return render(request, 'finance/expense_list.html', {
        'expenses': expenses,
        'categories': categories,
        'total': total,
        'selected_category': category_id,
        'date_from': date_from,
        'date_to': date_to,
    })


def expense_add_view(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense recorded.')
            if request.POST.get('add_another'):
                return redirect('finance:expense_add')
            return redirect('finance:expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'finance/expense_form.html', {'form': form, 'action': 'Add'})


def expense_edit_view(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated.')
            return redirect('finance:expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'finance/expense_form.html', {
        'form': form, 'expense': expense, 'action': 'Edit'
    })


def expense_delete_view(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted.')
        return redirect('finance:expense_list')
    return render(request, 'finance/expense_confirm_delete.html', {'expense': expense})


# ── Category management ───────────────────────────────────────────────────────

def category_list_view(request):
    categories = ExpenseCategory.objects.all()
    return render(request, 'finance/category_list.html', {'categories': categories})


def category_toggle_view(request, pk):
    """Toggle active/inactive on a category."""
    cat = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        cat.is_active = not cat.is_active
        cat.save(update_fields=['is_active'])
        state = 'activated' if cat.is_active else 'deactivated'
        messages.success(request, f'Category "{cat.name}" {state}.')
    return redirect('finance:category_list')
