from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from django.views.decorators.http import require_POST

from .models import OfficeServiceRecord, OfficeServicePayment, OfficeServiceRate, OfficeIncome
from .forms import OfficeServiceRecordForm, OfficeServicePaymentForm, OfficeServiceRateForm, OfficeIncomeForm
from accounts.decorators import login_required, editor_required, admin_required


# ── Office Service Records ──────────────────────────────────────────────────

@login_required
def service_list(request):
    qs = OfficeServiceRecord.objects.all()
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(client_name__icontains=search)

    # Summary stats
    total_charged = sum(r.total_charge for r in OfficeServiceRecord.objects.all())
    total_paid    = sum(r.total_paid   for r in OfficeServiceRecord.objects.all())
    total_balance = total_charged - total_paid

    active_rate = OfficeServiceRate.get_active()
    return render(request, 'office/service_list.html', {
        'records':       qs,
        'status_filter': status_filter,
        'search':        search,
        'status_choices': OfficeServiceRecord.STATUS_CHOICES,
        'total_charged': total_charged,
        'total_paid':    total_paid,
        'total_balance': total_balance,
        'active_rate':   active_rate,
    })


@editor_required
def service_create(request):
    if request.method == 'POST':
        form = OfficeServiceRecordForm(request.POST)
        if form.is_valid():
            record = form.save()
            messages.success(request, f'Office service record for {record.client_name} created.')
            return redirect('office:service_detail', pk=record.pk)
    else:
        form = OfficeServiceRecordForm()
    return render(request, 'office/service_form.html', {'form': form, 'action': 'Create'})


@login_required
def service_detail(request, pk):
    record = get_object_or_404(OfficeServiceRecord, pk=pk)
    payment_form = OfficeServicePaymentForm()
    return render(request, 'office/service_detail.html', {
        'record':       record,
        'payments':     record.payments.all(),
        'payment_form': payment_form,
    })


@editor_required
def service_edit(request, pk):
    record = get_object_or_404(OfficeServiceRecord, pk=pk)
    if request.method == 'POST':
        form = OfficeServiceRecordForm(request.POST, instance=record)
        if form.is_valid():
            record = form.save()
            messages.success(request, 'Record updated.')
            return redirect('office:service_detail', pk=record.pk)
    else:
        form = OfficeServiceRecordForm(instance=record)
    return render(request, 'office/service_form.html', {'form': form, 'record': record, 'action': 'Edit'})


@admin_required
def service_delete(request, pk):
    record = get_object_or_404(OfficeServiceRecord, pk=pk)
    if request.method == 'POST':
        record.delete()
        messages.success(request, 'Record deleted.')
        return redirect('office:service_list')
    return render(request, 'office/service_confirm_delete.html', {'record': record})


@editor_required
@require_POST
def service_add_payment(request, pk):
    record = get_object_or_404(OfficeServiceRecord, pk=pk)
    form = OfficeServicePaymentForm(request.POST)
    if form.is_valid():
        payment = form.save(commit=False)
        payment.record = record
        payment.save()
        # Update status
        total_paid = sum(p.amount for p in record.payments.all())
        if total_paid >= record.total_charge:
            record.status = 'paid'
            # Map OfficeServicePayment method → OfficeIncome account
            _method_map = {
                'cash': 'cash', 'bank_transfer': 'bank',
                'mobile_money': 'mpesa', 'cheque': 'cheque',
            }
            income_pm = _method_map.get(payment.payment_method, 'unspecified')
            OfficeIncome.objects.get_or_create(
                office_record=record,
                source='office_service',
                defaults={
                    'amount':         record.total_charge,
                    'date':           timezone.now().date(),
                    'description':    f'Office service – {record.client_name} ({record.num_windows}W/{record.num_doors}D)',
                    'payment_method': income_pm,
                }
            )
        elif total_paid > 0:
            record.status = 'partial'
        record.save(update_fields=['status'])
        messages.success(request, f'Payment of TZS {payment.amount:,.0f} recorded.')
    else:
        messages.error(request, 'Invalid payment.')
    return redirect('office:service_detail', pk=pk)


# ── Rates ───────────────────────────────────────────────────────────────────

@login_required
def rate_list(request):
    all_rates = OfficeServiceRate.objects.order_by('-effective_from')
    active_rate = OfficeServiceRate.get_active()
    if request.method == 'POST':
        from accounts.decorators import _get_role
        if _get_role(request.user) not in ('editor', 'admin'):
            messages.error(request, 'Huna ruhusa ya kubadilisha bei. Unahitaji nafasi ya Editor au Admin.')
            return redirect('office:rates')
        form = OfficeServiceRateForm(request.POST)
        if form.is_valid():
            OfficeServiceRate.objects.filter(is_active=True).update(is_active=False)
            rate = form.save(commit=False)
            rate.is_active = True   # force active regardless of form checkbox
            rate.save()
            messages.success(request, f'New rate set: TZS {rate.rate_per_window}/window · TZS {rate.rate_per_door}/door')
            return redirect('office:rates')
    else:
        form = OfficeServiceRateForm()
    return render(request, 'office/rates.html', {
        'all_rates':   all_rates,
        'active_rate': active_rate,
        'form':        form,
    })


# ── Income Overview ─────────────────────────────────────────────────────────

@login_required
def income_overview(request):
    from decimal import Decimal
    from datetime import date as _date
    from projects.models import Project as Proj

    D = Decimal
    METHOD_MAP = {
        'cash': 'cash', 'bank_transfer': 'bank',
        'mobile_money': 'mpesa', 'mpesa': 'mpesa',
        'bank': 'bank', 'cheque': 'cheque',
    }

    entries = []

    # ── 1. Project profits — always live from completed projects ─────────────
    project_total = D('0')
    for p in (Proj.objects.filter(status='completed')
                          .select_related('invoice')
                          .order_by('-completion_date')):
        profit = p.gross_profit
        entries.append({
            'date':           p.completion_date or p.start_date,
            'source':         'project_profit',
            'source_display': 'Project Profit',
            'project':        p,
            'office_record':  None,
            'description':    p.name,
            'payment_method': 'unspecified',
            'amount':         profit,
            'pk':             None,
        })
        project_total += profit

    # ── 2. Office service — total actually received per record ───────────────
    service_total = D('0')
    for rec in (OfficeServiceRecord.objects
                .filter(status__in=('paid', 'partial'))
                .prefetch_related('payments')
                .order_by('-created_at')):
        payments = list(rec.payments.all())
        if not payments:
            continue
        total_paid = sum(p.amount for p in payments)
        last_pay   = max(payments, key=lambda p: p.payment_date)
        pm = METHOD_MAP.get(last_pay.payment_method, 'unspecified')
        entries.append({
            'date':           last_pay.payment_date,
            'source':         'office_service',
            'source_display': 'Office Service',
            'project':        None,
            'office_record':  rec,
            'description':    f'{rec.client_name} ({rec.num_windows}W/{rec.num_doors}D)',
            'payment_method': pm,
            'amount':         total_paid,
            'pk':             None,
        })
        service_total += total_paid

    # ── 3. Other income — manual entries (always correct) ────────────────────
    other_total = D('0')
    for inc in OfficeIncome.objects.filter(source='other').order_by('-date'):
        entries.append({
            'date':           inc.date,
            'source':         'other',
            'source_display': 'Other Income',
            'project':        None,
            'office_record':  None,
            'description':    inc.description,
            'payment_method': inc.payment_method,
            'amount':         inc.amount,
            'pk':             inc.pk,
        })
        other_total += inc.amount

    grand_total = project_total + service_total + other_total

    # ── 4. Sort combined ledger newest-first ─────────────────────────────────
    entries.sort(key=lambda e: e['date'] or _date.min, reverse=True)

    # ── 5. Payment-method totals across all sources ───────────────────────────
    totals = {'cash': D('0'), 'bank': D('0'), 'mpesa': D('0')}
    for e in entries:
        key = METHOD_MAP.get(e['payment_method'])
        if key in totals:
            totals[key] += e['amount']

    return render(request, 'office/income.html', {
        'income_entries':  entries[:200],
        'project_total':   project_total,
        'service_total':   service_total,
        'other_total':     other_total,
        'grand_total':     grand_total,
        'cash_total':      totals['cash'],
        'bank_total':      totals['bank'],
        'mpesa_total':     totals['mpesa'],
        'account_choices': OfficeIncome.ACCOUNT_CHOICES,
    })


@editor_required
@require_POST
def income_add(request):
    description    = request.POST.get('description', '').strip()
    amount         = request.POST.get('amount')
    date           = request.POST.get('date')
    payment_method = request.POST.get('payment_method', 'unspecified')
    valid_methods  = [c[0] for c in OfficeIncome.ACCOUNT_CHOICES]
    if payment_method not in valid_methods:
        payment_method = 'unspecified'
    if description and amount and date:
        OfficeIncome.objects.create(
            source='other',
            description=description,
            amount=amount,
            date=date,
            payment_method=payment_method,
        )
        messages.success(request, 'Income record added.')
    else:
        messages.error(request, 'Please fill in all required fields.')
    return redirect('office:income')


@admin_required
@require_POST
def income_delete(request, pk):
    entry = get_object_or_404(OfficeIncome, pk=pk, source='other')
    entry.delete()
    messages.success(request, 'Income entry deleted.')
    return redirect('office:income')
