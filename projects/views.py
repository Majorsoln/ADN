from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Project, ProjectEvent
from .forms import ProjectForm
from office.models import OfficeIncome
from orders.models import MaterialOrder
from finance.models import Debt
from accounts.decorators import login_required, editor_required, admin_required


# ── helpers ──────────────────────────────────────────────────────────────────

def _log(project, event_type, description):
    ProjectEvent.objects.create(project=project, event_type=event_type, description=description)


def _funding_analysis(project, orders):
    """
    Build a full funding picture for a project:
    - How each material order was funded (cash/bank/mpesa/…)
    - Direct project expenses (transport, labour, site costs, etc.)
    - Client payments received (advance + InvoicePayments)
    - Shortfall or surplus vs total project cost
    """
    D = Decimal

    # ── Materials outflow by payment source ──────────────────────────────────
    funded = {}
    for order in orders:
        if order.status in ('ordered', 'partially_received', 'received'):
            ps = order.payment_source
            funded[ps] = funded.get(ps, D('0')) + order.total_cost

    source_labels = dict(orders[0].PAYMENT_SOURCE_CHOICES) if orders else {}
    mat_breakdown = [
        {'key': k, 'label': source_labels.get(k, k), 'amount': v}
        for k, v in sorted(funded.items(), key=lambda x: -x[1])
    ]

    # ── Direct project expenses (transport, labour, etc.) ────────────────────
    direct_expenses = list(
        project.expenses.select_related('category').order_by('date')
    )
    direct_expenses_cost = sum(e.amount for e in direct_expenses)

    # Group direct expenses by category for summary
    exp_cat_map = {}
    for exp in direct_expenses:
        cid = exp.category_id
        if cid not in exp_cat_map:
            exp_cat_map[cid] = {
                'name':  exp.category.name,
                'icon':  exp.category.icon,
                'color': exp.category.color,
                'total': D('0'),
            }
        exp_cat_map[cid]['total'] += exp.amount
    direct_expenses_by_cat = sorted(exp_cat_map.values(), key=lambda x: -x['total'])

    # ── Client money received ─────────────────────────────────────────────────
    if project.invoice:
        advance_paid = project.invoice.advance_paid
        inv_payments = list(
            project.invoice.payments.all().order_by('payment_date')
        )
        total_client_received = advance_paid + sum(p.amount for p in inv_payments)
    else:
        advance_paid = D('0')
        inv_payments = []
        total_client_received = D('0')

    # ── Net analysis ──────────────────────────────────────────────────────────
    materials_cost = project.materials_cost
    total_cost     = materials_cost + direct_expenses_cost

    # Shortfall: total cost NOT covered by what the client has already paid
    shortfall = max(total_cost - total_client_received, D('0'))
    # Surplus: client paid more than total cost (profit already banked)
    surplus   = max(total_client_received - total_cost, D('0'))

    # Credit orders: find linked debts
    credit_amount = funded.get('credit', D('0'))
    credit_orders = [o for o in orders if o.payment_source == 'credit'
                     and o.status in ('ordered', 'partially_received', 'received')]

    # Identify own-funds sources used when client hasn't covered total cost
    bank_used  = funded.get('bank', D('0'))
    cash_used  = funded.get('cash', D('0'))
    mpesa_used = funded.get('mpesa', D('0'))

    own_funds_message = None
    if shortfall > 0:
        parts = []
        if bank_used > 0:
            parts.append(f"Bank TZS {bank_used:,.0f}")
        if cash_used > 0:
            parts.append(f"Cash TZS {cash_used:,.0f}")
        if mpesa_used > 0:
            parts.append(f"M-Pesa TZS {mpesa_used:,.0f}")
        if credit_amount > 0:
            parts.append(f"Credit/Debt TZS {credit_amount:,.0f}")
        cost_desc = f"total project cost TZS {total_cost:,.0f}"
        if direct_expenses_cost > 0:
            cost_desc += f" (materials TZS {materials_cost:,.0f} + expenses TZS {direct_expenses_cost:,.0f})"
        if parts:
            own_funds_message = (
                f"Own funds contributed to cover TZS {shortfall:,.0f} shortfall "
                f"(client paid TZS {total_client_received:,.0f} vs {cost_desc}): "
                + " + ".join(parts)
            )
        else:
            own_funds_message = (
                f"{cost_desc.capitalize()} exceeds client payments "
                f"received (TZS {total_client_received:,.0f}). "
                f"Shortfall TZS {shortfall:,.0f} — source unspecified."
            )

    # Balance still owed by client
    balance_due = max(project.revenue - total_client_received, D('0'))

    # ── Project-linked debts (what the business owes for this project) ───────
    project_debts = list(
        Debt.objects.filter(project=project)
        .exclude(status='settled')
        .prefetch_related('payments')
    )
    project_debts_total = sum(d.balance for d in project_debts)

    # ── Consolidated funds used (materials + expenses by payment source) ─────
    # Merge all outflows into a single per-source view
    funds_used = {}
    # Materials by payment source
    for order in orders:
        if order.status in ('ordered', 'partially_received', 'received'):
            ps = order.payment_source
            key = 'credit' if ps == 'credit' else ps
            if key not in funds_used:
                funds_used[key] = {'materials': D('0'), 'expenses': D('0')}
            funds_used[key]['materials'] += order.total_cost
    # Expenses by payment method
    for exp in direct_expenses:
        m = exp.payment_method
        if m not in funds_used:
            funds_used[m] = {'materials': D('0'), 'expenses': D('0')}
        funds_used[m]['expenses'] += exp.amount

    source_info = {
        'cash':   {'label': 'Office Cash',    'icon': 'cash',   'color': '#16a34a'},
        'bank':   {'label': 'Bank Account',   'icon': 'bank',   'color': '#2563eb'},
        'mpesa':  {'label': 'M-Pesa',         'icon': 'mpesa',  'color': '#059669'},
        'cheque': {'label': 'Cheque',         'icon': 'cheque', 'color': '#7c3aed'},
        'credit': {'label': 'Deni (Credit)',  'icon': 'credit', 'color': '#dc2626'},
        'other':  {'label': 'Other',          'icon': 'other',  'color': '#94a3b8'},
    }
    funds_used_rows = []
    for key, vals in sorted(funds_used.items(), key=lambda x: -(x[1]['materials'] + x[1]['expenses'])):
        info = source_info.get(key, source_info['other'])
        total = vals['materials'] + vals['expenses']
        funds_used_rows.append({
            'key':       key,
            'label':     info['label'],
            'color':     info['color'],
            'materials': vals['materials'],
            'expenses':  vals['expenses'],
            'total':     total,
            'is_debt':   key == 'credit',
        })

    # Advance payment method label
    advance_method = ''
    if project.invoice and advance_paid > 0:
        m = project.invoice.advance_payment_method or ''
        method_labels = {
            'cash': 'Cash', 'bank_transfer': 'Bank', 'bank': 'Bank',
            'mobile_money': 'M-Pesa', 'mpesa': 'M-Pesa',
            'cheque': 'Cheque',
        }
        advance_method = method_labels.get(m, m.replace('_', ' ').title() if m else '')

    return {
        'mat_breakdown':           mat_breakdown,
        'advance_paid':            advance_paid,
        'advance_method':          advance_method,
        'inv_payments':            inv_payments,
        'total_client_received':   total_client_received,
        'balance_due':             balance_due,
        'materials_cost':          materials_cost,
        'direct_expenses':         direct_expenses,
        'direct_expenses_cost':    direct_expenses_cost,
        'direct_expenses_by_cat':  direct_expenses_by_cat,
        'total_cost':              total_cost,
        'shortfall':               shortfall,
        'surplus':                 surplus,
        'own_funds_message':       own_funds_message,
        'credit_orders':           credit_orders,
        'credit_amount':           credit_amount,
        'project_debts':           project_debts,
        'project_debts_total':     project_debts_total,
        'funds_used_rows':         funds_used_rows,
    }


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
def list_view(request):
    qs = Project.objects.all()
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(name__icontains=search) | qs.filter(client_name__icontains=search)

    projects = list(qs)

    # Pre-group for pipeline view
    STAGES = [
        ('planning',    'Planning',          '#64748b'),
        ('ordered',     'Materials Ordered', '#d97706'),
        ('in_progress', 'In Progress',       '#2563eb'),
        ('completed',   'Completed',         '#16a34a'),
    ]
    pipeline = [
        (val, label, color, [p for p in projects if p.status == val])
        for val, label, color in STAGES
    ]

    return render(request, 'projects/list.html', {
        'projects':      projects,
        'pipeline':      pipeline,
        'status_filter': status_filter,
        'search':        search,
        'status_choices': Project.STATUS_CHOICES,
        'today':         timezone.now().date(),
    })


@editor_required
def create_view(request):
    # Pre-fill from quotation
    quote_pk = request.GET.get('from_quote')
    initial = {}
    locked_quotation = None
    if quote_pk:
        from quotations.models import Quotation
        try:
            locked_quotation = Quotation.objects.get(pk=quote_pk)
            initial = {
                'name':         locked_quotation.project_name or f"Project – {locked_quotation.client_name}",
                'client_name':  locked_quotation.client_name,
                'client_phone': locked_quotation.client_phone,
                'quotation':    locked_quotation,
            }
        except Quotation.DoesNotExist:
            pass

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            desc = f'Project "{project.name}" created for client {project.client_name}.'
            if project.quotation:
                desc += f' Linked to quotation {project.quotation.quote_no}.'
            _log(project, 'created', desc)
            messages.success(request, f'Project "{project.name}" created.')
            return redirect('projects:detail', pk=project.pk)
    else:
        form = ProjectForm(initial=initial)

    return render(request, 'projects/form.html', {
        'form':             form,
        'action':           'Create',
        'locked_quotation': locked_quotation,
    })


@login_required
def detail_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    orders  = list(project.orders.prefetch_related('items').all())
    all_events = project.events.all()
    funding = _funding_analysis(project, orders)
    return render(request, 'projects/detail.html', {
        'project':       project,
        'orders':        orders,
        'events':        all_events[:40],
        'events_total':  all_events.count(),
        'funding':                funding,
        'payment_source_choices': MaterialOrder.PAYMENT_SOURCE_CHOICES,
    })


@editor_required
def edit_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    old_status  = project.status
    old_invoice = project.invoice_id
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            project = form.save()
            if project.status != old_status:
                _log(project, 'status',
                     f'Status changed: {dict(Project.STATUS_CHOICES).get(old_status)} → '
                     f'{project.get_status_display()}')
            if project.invoice_id and project.invoice_id != old_invoice:
                _log(project, 'invoice',
                     f'Invoice {project.invoice.invoice_no} linked.')
            messages.success(request, f'Project "{project.name}" updated.')
            return redirect('projects:detail', pk=project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'projects/form.html', {
        'form':             form,
        'project':          project,
        'action':           'Edit',
        'locked_quotation': project.quotation,  # Show locked card for existing link
    })


@admin_required
def delete_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'Project "{name}" deleted.')
        return redirect('projects:list')
    return render(request, 'projects/confirm_delete.html', {'project': project})


@login_required
def report_view(request, pk):
    """Final project report — printable as PDF."""
    project = get_object_or_404(Project, pk=pk)
    orders  = list(project.orders.prefetch_related('items').all())
    events  = project.events.all()
    funding = _funding_analysis(project, orders)
    return render(request, 'projects/report.html', {
        'project': project,
        'orders':  orders,
        'events':  events,
        'funding': funding,
        'today':   timezone.now().date(),
    })


@editor_required
def complete_view(request, pk):
    """Mark project completed and record gross profit to OfficeIncome."""
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'unspecified')
        valid_methods = [c[0] for c in OfficeIncome.ACCOUNT_CHOICES]
        if payment_method not in valid_methods:
            payment_method = 'unspecified'
        project.status = 'completed'
        project.completion_date = timezone.now().date()
        project.save()
        profit = project.gross_profit
        if profit > 0:
            OfficeIncome.objects.get_or_create(
                project=project,
                source='project_profit',
                defaults={
                    'amount':          profit,
                    'date':            project.completion_date,
                    'description':     f'Profit from project: {project.name}',
                    'payment_method':  payment_method,
                }
            )
        method_label = dict(OfficeIncome.ACCOUNT_CHOICES).get(payment_method, '')
        _log(project, 'completed',
             f'Project marked completed. Gross profit TZS {profit:,.0f} recorded to office income ({method_label}).')
        messages.success(request, f'Project completed. TZS {profit:,.0f} profit recorded ({method_label}).')
        return redirect('projects:report', pk=pk)
    return render(request, 'projects/confirm_complete.html', {
        'project': project,
        'payment_choices': OfficeIncome.ACCOUNT_CHOICES,
    })


@editor_required
@require_POST
def add_note_view(request, pk):
    """Add a manual note to the project timeline."""
    project = get_object_or_404(Project, pk=pk)
    note = request.POST.get('note', '').strip()
    if note:
        _log(project, 'note', note)
        messages.success(request, 'Note added to project timeline.')
    return redirect('projects:detail', pk=pk)


@editor_required
@require_POST
def update_status_view(request, pk):
    """Quick status update from project detail page."""
    project = get_object_or_404(Project, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in Project.STATUS_CHOICES]
    if new_status in valid and new_status != project.status:
        old_label = project.get_status_display()
        project.status = new_status
        if new_status == 'completed' and not project.completion_date:
            project.completion_date = timezone.now().date()
        project.save()
        _log(project, 'status',
             f'Status changed: {old_label} → {project.get_status_display()}')
        # Record profit to OfficeIncome when marked completed (same as complete_view)
        if new_status == 'completed':
            profit = project.gross_profit
            if profit > 0:
                OfficeIncome.objects.get_or_create(
                    project=project,
                    source='project_profit',
                    defaults={
                        'amount':         profit,
                        'date':           project.completion_date,
                        'description':    f'Profit from project: {project.name}',
                        'payment_method': 'unspecified',
                    }
                )
        messages.success(request, f'Status updated to {project.get_status_display()}.')
    return redirect('projects:detail', pk=pk)
