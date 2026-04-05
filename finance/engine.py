"""
finance/engine.py
-----------------
Report computation engine.  All heavy number-crunching lives here so
views stay thin and templates stay dumb.

Public API
~~~~~~~~~~
    compute_snapshot(date=None)   → dict   (Level-1 owner daily view)
    compute_report(date_from, date_to) → dict  (Level-2/3 full report)
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from invoices.models import Invoice, InvoicePayment
from office.models import OfficeServiceRecord, OfficeServicePayment, OfficeIncome
from orders.models import MaterialOrder
from projects.models import Project
from finance.models import Expense, ExpenseCategory, Debt, DebtPayment


# ── helpers ──────────────────────────────────────────────────────────────────

def _d(value):
    """Safely coerce a value to Decimal (avoids None or float issues)."""
    if value is None:
        return Decimal('0')
    return Decimal(str(value))


def _sum_qs(qs, field):
    """Aggregate a queryset field and return Decimal."""
    return _d(qs.aggregate(s=Sum(field))['s'])


def _month_range(year, month):
    """Return (first_day, last_day) of a given month."""
    from calendar import monthrange
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last


# ── Income aggregation ────────────────────────────────────────────────────────

def _invoice_payments_in(date_from, date_to):
    """Sum of InvoicePayment amounts in period."""
    qs = InvoicePayment.objects.filter(payment_date__gte=date_from, payment_date__lte=date_to)
    return _sum_qs(qs, 'amount'), list(qs.select_related('invoice').order_by('-payment_date'))


def _office_payments_in(date_from, date_to):
    """Sum of OfficeServicePayment amounts in period."""
    qs = OfficeServicePayment.objects.filter(payment_date__gte=date_from, payment_date__lte=date_to)
    return _sum_qs(qs, 'amount'), list(qs.select_related('record').order_by('-payment_date'))


def _other_income_in(date_from, date_to):
    """Sum of OfficeIncome records with source='other' in period."""
    qs = OfficeIncome.objects.filter(source='other', date__gte=date_from, date__lte=date_to)
    return _sum_qs(qs, 'amount'), list(qs)


def _advance_payments_in(date_from, date_to):
    """
    Sum of Invoice.advance_paid for invoices created in period.
    Advance is typically collected at invoice creation time — we use
    invoice_date as the proxy for when the cash/bank was received.
    Returns (total, rows_list, by_method_dict).
    """
    qs = Invoice.objects.filter(
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
        advance_paid__gt=0,
    )
    total = _d(qs.aggregate(s=Sum('advance_paid'))['s'])
    rows = list(qs.only(
        'invoice_no', 'client_name', 'advance_paid',
        'advance_payment_method', 'invoice_date',
    ))
    # Group by method
    by_method = {}
    for inv in rows:
        m = inv.advance_payment_method or 'unspecified'
        by_method[m] = by_method.get(m, Decimal('0')) + inv.advance_paid
    return total, rows, by_method


# ── Expense aggregation ───────────────────────────────────────────────────────

def _expenses_in(date_from, date_to):
    """
    Returns (total, by_category_list, expense_rows,
             project_expenses_total, office_expenses_total).

    Expenses are split into:
      - project_expenses: linked to a specific project (transport, labour, site, etc.)
      - office_expenses:  general office/operational overhead (no project link)

    by_category_list: [{'name', 'icon', 'color', 'total', 'project_total', 'office_total'}, ...]
    """
    qs = (Expense.objects
          .filter(date__gte=date_from, date__lte=date_to)
          .select_related('category', 'project'))
    total = Decimal('0')
    project_total = Decimal('0')
    office_total  = Decimal('0')
    cat_map = {}
    rows = list(qs.order_by('-date'))
    for exp in rows:
        total += exp.amount
        is_project = bool(exp.project_id)
        if is_project:
            project_total += exp.amount
        else:
            office_total  += exp.amount

        cid = exp.category_id
        if cid not in cat_map:
            cat_map[cid] = {
                'name':          exp.category.name,
                'icon':          exp.category.icon,
                'color':         exp.category.color,
                'total':         Decimal('0'),
                'project_total': Decimal('0'),
                'office_total':  Decimal('0'),
                'count':         0,
            }
        cat_map[cid]['total']  += exp.amount
        cat_map[cid]['count']  += 1
        if is_project:
            cat_map[cid]['project_total'] += exp.amount
        else:
            cat_map[cid]['office_total']  += exp.amount

    by_category = sorted(cat_map.values(), key=lambda x: x['total'], reverse=True)
    return total, by_category, rows, project_total, office_total


# ── Receivables (Python loop — properties not DB-aggregatable) ───────────────

def _invoice_receivables():
    """Outstanding invoice balances (unpaid / partially paid)."""
    qs = Invoice.objects.filter(status__in=['draft', 'sent', 'overdue'])
    total = Decimal('0')
    overdue_count = 0
    overdue_amount = Decimal('0')
    rows = []
    for inv in qs.prefetch_related('payments'):
        bal = inv.balance_due
        if bal <= 0:
            continue
        total += bal
        is_ov = inv.is_overdue
        if is_ov:
            overdue_count += 1
            overdue_amount += bal
        rows.append({
            'invoice_no': inv.invoice_no,
            'client_name': inv.client_name,
            'balance': bal,
            'due_date': inv.due_date,
            'is_overdue': is_ov,
            'pk': inv.pk,
        })
    rows.sort(key=lambda r: (not r['is_overdue'], r['due_date'] or date.max))
    return total, overdue_count, overdue_amount, rows


def _service_receivables():
    """Outstanding office service record balances."""
    qs = OfficeServiceRecord.objects.exclude(status='paid').prefetch_related('payments')
    total = Decimal('0')
    overdue_count = 0
    overdue_amount = Decimal('0')
    rows = []
    for rec in qs:
        bal = rec.balance
        if bal <= 0:
            continue
        total += bal
        is_ov = rec.is_overdue
        if is_ov:
            overdue_count += 1
            overdue_amount += bal
        rows.append({
            'client_name': rec.client_name,
            'balance': bal,
            'due_date': rec.due_date,
            'is_overdue': is_ov,
            'pk': rec.pk,
        })
    rows.sort(key=lambda r: (not r['is_overdue'], r['due_date'] or date.max))
    return total, overdue_count, overdue_amount, rows


# ── Project stats ─────────────────────────────────────────────────────────────

def _liabilities_summary():
    """
    Current total liabilities (all outstanding / partial debts).
    Returns dict with totals and breakdown by type.
    """
    debts = list(Debt.objects.exclude(status='settled').prefetch_related('payments'))

    total_owed    = sum(d.amount    for d in debts)
    total_paid    = sum(d.total_paid for d in debts)
    total_balance = sum(d.balance   for d in debts)
    overdue       = [d for d in debts if d.is_overdue]
    overdue_amount = sum(d.balance  for d in overdue)

    # Breakdown by type
    by_type = {}
    for d in debts:
        key = d.debt_type
        if key not in by_type:
            by_type[key] = {'label': d.get_debt_type_display(), 'balance': Decimal('0'), 'count': 0}
        by_type[key]['balance'] += d.balance
        by_type[key]['count']   += 1

    return {
        'total_owed':      float(total_owed),
        'total_paid':      float(total_paid),
        'total_balance':   float(total_balance),
        'overdue_count':   len(overdue),
        'overdue_amount':  float(overdue_amount),
        'by_type': [
            {'type': k, 'label': v['label'],
             'balance': float(v['balance']), 'count': v['count']}
            for k, v in by_type.items()
        ],
    }


def _project_stats(date_from, date_to):
    """Projects completed in period, revenue/profit aggregated via Python."""
    completed = Project.objects.filter(
        status='completed',
        completion_date__gte=date_from,
        completion_date__lte=date_to,
    ).select_related('invoice').prefetch_related('orders', 'expenses')

    total_revenue    = Decimal('0')
    total_materials  = Decimal('0')
    total_dir_exp    = Decimal('0')
    total_profit     = Decimal('0')
    project_rows     = []

    for p in completed:
        rev     = p.revenue
        mat     = p.materials_cost
        dir_exp = p.direct_expenses_cost
        profit  = p.gross_profit   # revenue - materials - direct_expenses
        total_revenue   += rev
        total_materials += mat
        total_dir_exp   += dir_exp
        total_profit    += profit
        project_rows.append({
            'name':                  p.name,
            'client_name':           p.client_name,
            'completion_date':       p.completion_date,
            'revenue':               rev,
            'materials_cost':        mat,
            'direct_expenses_cost':  dir_exp,
            'total_cost':            mat + dir_exp,
            'gross_profit':          profit,
            'profit_margin':         float(p.profit_margin),
            'pk':                    p.pk,
        })

    margin = (total_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0')
    return {
        'count':             len(project_rows),
        'total_revenue':     total_revenue,
        'total_materials':   total_materials,
        'total_direct_exp':  total_dir_exp,
        'total_profit':      total_profit,
        'profit_margin':     float(margin),
        'projects':          project_rows,
    }


# ── Monthly trend (last N months) ────────────────────────────────────────────

def _monthly_trends(months=6):
    """
    Returns list of monthly dicts ordered oldest→newest:
    [{'label', 'income', 'expenses', 'net'}, ...]
    """
    today = timezone.now().date()
    result = []
    for i in range(months - 1, -1, -1):
        # walk backwards from current month
        target_month = today.month - i
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        first, last = _month_range(target_year, target_month)
        label = first.strftime('%b %Y')

        inv_income, _ = _invoice_payments_in(first, last)
        off_income, _ = _office_payments_in(first, last)
        oth_income, _ = _other_income_in(first, last)
        income = inv_income + off_income + oth_income

        exp_total, _, _, _, _ = _expenses_in(first, last)

        result.append({
            'label': label,
            'income': float(income),
            'expenses': float(exp_total),
            'net': float(income - exp_total),
        })
    return result


# ── Alerts ────────────────────────────────────────────────────────────────────

def _build_alerts(inv_overdue_count, inv_overdue_amt,
                  svc_overdue_count, svc_overdue_amt,
                  by_category, total_expenses,
                  debt_overdue_count=0, debt_overdue_amount=0):
    alerts = []
    if debt_overdue_count:
        alerts.append({
            'level': 'danger',
            'icon': 'bi-exclamation-triangle-fill',
            'message': (
                f"{debt_overdue_count} debt(s) overdue — "
                f"TZS {debt_overdue_amount:,.0f} still owed"
            ),
        })
    if inv_overdue_count:
        alerts.append({
            'level': 'danger',
            'icon': 'bi-exclamation-triangle-fill',
            'message': (
                f"{inv_overdue_count} invoice(s) overdue — "
                f"TZS {inv_overdue_amt:,.0f} outstanding"
            ),
        })
    if svc_overdue_count:
        alerts.append({
            'level': 'warning',
            'icon': 'bi-clock-history',
            'message': (
                f"{svc_overdue_count} office service record(s) overdue — "
                f"TZS {svc_overdue_amt:,.0f} outstanding"
            ),
        })
    # Flag any category that is >40% of total expenses (only if meaningful amount)
    if total_expenses > 0:
        for cat in by_category:
            pct = float(cat['total']) / float(total_expenses) * 100
            if pct > 40 and float(cat['total']) > 50_000:
                alerts.append({
                    'level': 'warning',
                    'icon': 'bi-bar-chart-line',
                    'message': (
                        f"High spend: {cat['name']} is {pct:.0f}% of total expenses "
                        f"(TZS {cat['total']:,.0f})"
                    ),
                })
    return alerts


# ── Funds position (all-time balance sheet view) ──────────────────────────────

def _funds_position():
    """
    ALL-TIME view: where is the business money right now?

    For each account (Cash / Bank / M-Pesa / Cheque):
        balance = all_inflows_via_that_method - all_outflows_via_that_method

    Inflows:
        InvoicePayment   (payment_method)
        Invoice.advance_paid  (advance_payment_method)
        OfficeServicePayment (payment_method)

    Outflows (non-credit, already paid):
        Expense          (payment_method)
        MaterialOrder    (payment_source, status in ordered/partially/received, NOT credit)

    Credit we owe (not yet paid from any account):
        Debt.balance  — broken down: supplier_credit, labour_credit, other

    Credit clients owe us:
        Invoice.balance_due  (for unpaid/partial invoices)
        OfficeServiceRecord.balance
    """
    D = Decimal

    # ── Helpers: normalise method names to canonical keys ──────────────────
    # All three source models use slightly different choice values.
    # We map everything → 'cash' | 'bank' | 'mpesa' | 'cheque' | 'other'
    def _norm_in(method):
        m = (method or '').lower()
        if m == 'cash':              return 'cash'
        if m in ('bank_transfer', 'bank'): return 'bank'
        if m in ('mobile_money', 'mpesa'): return 'mpesa'
        if m == 'cheque':            return 'cheque'
        return 'other'

    def _norm_out(source):
        s = (source or '').lower()
        if s == 'cash':   return 'cash'
        if s == 'bank':   return 'bank'
        if s == 'mpesa':  return 'mpesa'
        if s == 'cheque': return 'cheque'
        return 'other'

    accounts = {k: {'in': D('0'), 'out': D('0')} for k in ['cash', 'bank', 'mpesa', 'cheque', 'other']}

    # ── INFLOWS ────────────────────────────────────────────────────────────

    # 1. Invoice instalment payments
    for p in InvoicePayment.objects.all().only('amount', 'payment_method'):
        accounts[_norm_in(p.payment_method)]['in'] += p.amount

    # 2. Advance payments on invoices
    for inv in Invoice.objects.filter(advance_paid__gt=0).only('advance_paid', 'advance_payment_method'):
        accounts[_norm_in(inv.advance_payment_method)]['in'] += inv.advance_paid

    # 3. Office service payments
    for p in OfficeServicePayment.objects.all().only('amount', 'payment_method'):
        accounts[_norm_in(p.payment_method)]['in'] += p.amount

    # ── OUTFLOWS (real money paid, not credit) ─────────────────────────────

    # 4. General expenses
    for exp in Expense.objects.all().only('amount', 'payment_method'):
        accounts[_norm_out(exp.payment_method)]['out'] += exp.amount

    # 5. Material orders paid via cash/bank/mpesa/cheque (not credit/unspecified)
    paid_sources = ('cash', 'bank', 'mpesa', 'cheque')
    for order in MaterialOrder.objects.filter(
        payment_source__in=paid_sources,
        status__in=['ordered', 'partially_received', 'received'],
    ).prefetch_related('items'):
        accounts[_norm_out(order.payment_source)]['out'] += order.total_cost

    # ── CREDIT WE OWE (Payables) ───────────────────────────────────────────
    outstanding_debts = list(
        Debt.objects.exclude(status='settled').prefetch_related('payments')
    )
    material_credit  = sum(d.balance for d in outstanding_debts if d.debt_type == 'supplier_credit')
    labour_credit    = sum(d.balance for d in outstanding_debts if d.debt_type == 'labour_credit')
    other_payable    = sum(d.balance for d in outstanding_debts
                          if d.debt_type not in ('supplier_credit', 'labour_credit'))
    total_payable    = material_credit + labour_credit + other_payable

    # ── CREDIT CLIENTS OWE US (Receivables) ────────────────────────────────
    inv_receivable = sum(
        inv.balance_due
        for inv in Invoice.objects.filter(
            status__in=['draft', 'sent', 'overdue']
        ).prefetch_related('payments')
        if inv.balance_due > 0
    )
    svc_receivable = sum(
        rec.balance
        for rec in OfficeServiceRecord.objects.exclude(status='paid')
        .prefetch_related('payments')
        if rec.balance > 0
    )
    total_receivable = inv_receivable + svc_receivable

    # ── SUMMARY ────────────────────────────────────────────────────────────
    account_labels = {
        'cash':   ('Cash',           'bi-cash-coin',    '#16a34a'),
        'bank':   ('Bank Transfer',  'bi-bank',         '#2563eb'),
        'mpesa':  ('M-Pesa',         'bi-phone',        '#059669'),
        'cheque': ('Cheque',         'bi-file-text',    '#7c3aed'),
        'other':  ('Other',          'bi-three-dots',   '#94a3b8'),
    }
    account_rows = []
    total_liquid = D('0')
    for key, vals in accounts.items():
        bal = vals['in'] - vals['out']
        if vals['in'] == 0 and vals['out'] == 0:
            continue
        label, icon, color = account_labels[key]
        account_rows.append({
            'key':     key,
            'label':   label,
            'icon':    icon,
            'color':   color,
            'in':      float(vals['in']),
            'out':     float(vals['out']),
            'balance': float(bal),
        })
        total_liquid += bal

    # Net position = liquid + receivables - payables
    net_position = total_liquid + total_receivable - total_payable

    return {
        'accounts':          account_rows,
        'total_liquid':      float(total_liquid),
        'inv_receivable':    float(inv_receivable),
        'svc_receivable':    float(svc_receivable),
        'total_receivable':  float(total_receivable),
        'material_credit':   float(material_credit),
        'labour_credit':     float(labour_credit),
        'other_payable':     float(other_payable),
        'total_payable':     float(total_payable),
        'net_position':      float(net_position),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def compute_snapshot(for_date=None):
    """
    Level-1 Owner Daily Snapshot.
    Returns a flat dict with today's cash flows + live receivable totals.
    """
    today = for_date or timezone.now().date()

    inv_income,  inv_payments           = _invoice_payments_in(today, today)
    off_income,  off_payments           = _office_payments_in(today, today)
    oth_income,  oth_records            = _other_income_in(today, today)
    adv_income,  adv_rows, adv_by_meth  = _advance_payments_in(today, today)
    total_in = inv_income + off_income + oth_income + adv_income

    exp_total, by_category, exp_rows, proj_exp_total, office_exp_total = _expenses_in(today, today)
    funds = _funds_position()

    inv_recv, inv_ov_c, inv_ov_a, inv_recv_rows = _invoice_receivables()
    svc_recv, svc_ov_c, svc_ov_a, svc_recv_rows = _service_receivables()
    total_receivable = inv_recv + svc_recv

    liabilities = _liabilities_summary()
    alerts = _build_alerts(
        inv_ov_c, inv_ov_a, svc_ov_c, svc_ov_a, by_category, exp_total,
        debt_overdue_count=liabilities['overdue_count'],
        debt_overdue_amount=liabilities['overdue_amount'],
    )

    return {
        'date': today,
        'total_in': total_in,
        'total_out': exp_total,
        'net_today': total_in - exp_total,
        # Breakdown of inflows
        'invoice_income': inv_income,
        'advance_income': adv_income,
        'advance_rows':   adv_rows,
        'office_income':  off_income,
        'other_income':   oth_income,
        'inv_payments':   inv_payments,
        'off_payments':   off_payments,
        # Expenses today
        'expenses': exp_rows,
        'by_category': by_category,
        'project_expenses_total': proj_exp_total,
        'office_expenses_total':  office_exp_total,
        # Live receivable totals (all-time outstanding, not filtered to today)
        'total_receivable': total_receivable,
        'invoice_receivable': inv_recv,
        'service_receivable': svc_recv,
        'invoice_overdue_count': inv_ov_c,
        'invoice_overdue_amount': inv_ov_a,
        'service_overdue_count': svc_ov_c,
        'service_overdue_amount': svc_ov_a,
        'invoice_recv_rows': inv_recv_rows,
        'service_recv_rows': svc_recv_rows,
        # Liabilities
        'liabilities': liabilities,
        # Funds position (all-time: where is the money)
        'funds': funds,
        'alerts': alerts,
    }


def compute_report(date_from, date_to):
    """
    Level-2 Business Report + Level-3 Accounting Detail.
    Returns a comprehensive dict suitable for storing in ReportSnapshot.figures.
    """
    # ── Income ────────────────────────────────────────────────────────────────
    inv_income,  inv_payments            = _invoice_payments_in(date_from, date_to)
    off_income,  off_payments            = _office_payments_in(date_from, date_to)
    oth_income,  oth_records             = _other_income_in(date_from, date_to)
    adv_income,  adv_rows, adv_by_meth   = _advance_payments_in(date_from, date_to)
    total_income = inv_income + off_income + oth_income + adv_income

    # ── Expenses ──────────────────────────────────────────────────────────────
    total_expenses, by_category, expense_rows, proj_exp_total, office_exp_total = _expenses_in(date_from, date_to)

    # ── Net ───────────────────────────────────────────────────────────────────
    net_profit = total_income - total_expenses

    # ── Receivables ───────────────────────────────────────────────────────────
    inv_recv, inv_ov_c, inv_ov_a, inv_recv_rows = _invoice_receivables()
    svc_recv, svc_ov_c, svc_ov_a, svc_recv_rows = _service_receivables()
    total_receivable = inv_recv + svc_recv

    # ── Project performance ───────────────────────────────────────────────────
    project_stats = _project_stats(date_from, date_to)

    # ── Monthly trends ────────────────────────────────────────────────────────
    trends = _monthly_trends(months=6)

    # ── Liabilities ───────────────────────────────────────────────────────────
    liabilities = _liabilities_summary()

    # ── Funds position (all-time) ─────────────────────────────────────────────
    funds = _funds_position()

    # ── Alerts ────────────────────────────────────────────────────────────────
    alerts = _build_alerts(
        inv_ov_c, inv_ov_a, svc_ov_c, svc_ov_a, by_category, total_expenses,
        debt_overdue_count=liabilities['overdue_count'],
        debt_overdue_amount=liabilities['overdue_amount'],
    )

    # ── Income breakdown (for ledger / journal view) ──────────────────────────
    income_breakdown = [
        {'source': 'Invoice Payments (Instalments)', 'amount': float(inv_income)},
        {'source': 'Invoice Advance Payments',        'amount': float(adv_income)},
        {'source': 'Office Service Fees',             'amount': float(off_income)},
        {'source': 'Other Income',                    'amount': float(oth_income)},
    ]

    return {
        # Summary
        'date_from': str(date_from),
        'date_to': str(date_to),
        'total_income': float(total_income),
        'total_expenses': float(total_expenses),
        'net_profit': float(net_profit),
        'profit_margin': float((net_profit / total_income * 100) if total_income else 0),

        # Income detail
        'invoice_income':  float(inv_income),
        'advance_income':  float(adv_income),
        'advance_by_method': {k: float(v) for k, v in adv_by_meth.items()},
        'advance_rows': [
            {
                'invoice_no':   inv.invoice_no,
                'client_name':  inv.client_name,
                'amount':       float(inv.advance_paid),
                'method':       inv.advance_payment_method,
                'invoice_date': str(inv.invoice_date),
            }
            for inv in adv_rows
        ],
        'office_income':   float(off_income),
        'other_income':    float(oth_income),
        'income_breakdown': income_breakdown,
        'inv_payments': [
            {
                'invoice_no': p.invoice.invoice_no,
                'client_name': p.invoice.client_name,
                'amount': float(p.amount),
                'payment_date': str(p.payment_date),
                'payment_method': p.payment_method,
            }
            for p in inv_payments
        ],
        'off_payments': [
            {
                'client_name': p.record.client_name,
                'amount': float(p.amount),
                'payment_date': str(p.payment_date),
                'payment_method': p.payment_method,
            }
            for p in off_payments
        ],

        # Expense detail (split: project vs office)
        'project_expenses_total': float(proj_exp_total),
        'office_expenses_total':  float(office_exp_total),
        'by_category': [
            {
                'name':          c['name'],
                'icon':          c['icon'],
                'color':         c['color'],
                'total':         float(c['total']),
                'project_total': float(c['project_total']),
                'office_total':  float(c['office_total']),
                'count':         c['count'],
                'pct': round(float(c['total']) / float(total_expenses) * 100, 1) if total_expenses else 0,
            }
            for c in by_category
        ],
        'expense_rows': [
            {
                'date':            str(e.date),
                'category':        e.category.name,
                'description':     e.description,
                'paid_to':         e.paid_to,
                'payment_method':  e.payment_method,
                'amount':          float(e.amount),
                'project_name':    e.project.name if e.project_id else None,
                'project_pk':      e.project_id,
            }
            for e in expense_rows
        ],

        # Receivables
        'total_receivable': float(total_receivable),
        'invoice_receivable': float(inv_recv),
        'service_receivable': float(svc_recv),
        'invoice_overdue_count': inv_ov_c,
        'invoice_overdue_amount': float(inv_ov_a),
        'service_overdue_count': svc_ov_c,
        'service_overdue_amount': float(svc_ov_a),
        'invoice_recv_rows': [
            {**r, 'balance': float(r['balance']), 'due_date': str(r['due_date'])}
            for r in inv_recv_rows
        ],
        'service_recv_rows': [
            {**r, 'balance': float(r['balance']),
             'due_date': str(r['due_date']) if r['due_date'] else None}
            for r in svc_recv_rows
        ],

        # Projects
        'project_stats': {
            **project_stats,
            'total_revenue':    float(project_stats['total_revenue']),
            'total_materials':  float(project_stats['total_materials']),
            'total_direct_exp': float(project_stats['total_direct_exp']),
            'total_profit':     float(project_stats['total_profit']),
            'projects': [
                {**p,
                 'revenue':               float(p['revenue']),
                 'materials_cost':        float(p['materials_cost']),
                 'direct_expenses_cost':  float(p['direct_expenses_cost']),
                 'total_cost':            float(p['total_cost']),
                 'gross_profit':          float(p['gross_profit']),
                 'completion_date':       str(p['completion_date'])}
                for p in project_stats['projects']
            ],
        },

        # Trends
        'monthly_trends': trends,

        # Liabilities
        'liabilities': liabilities,

        # Funds position (all-time: where is the money)
        'funds': funds,

        # Alerts
        'alerts': alerts,
    }
