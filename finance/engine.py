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
             project_expenses_total, office_expenses_total, credit_total).

    total           = ALL expenses in period (P&L basis, includes credit).
    credit_total    = subset paid on credit (Debt created; no cash moved).
    cash_total      = total - credit_total  (actual cash/bank paid out).

    by_category_list: [{'name', 'icon', 'color', 'total', 'credit_total',
                         'project_total', 'office_total', 'count'}, ...]
    """
    qs = (Expense.objects
          .filter(date__gte=date_from, date__lte=date_to)
          .select_related('category', 'project'))
    total        = Decimal('0')
    credit_total = Decimal('0')
    project_total = Decimal('0')
    office_total  = Decimal('0')
    cat_map = {}
    rows = list(qs.order_by('-date'))
    for exp in rows:
        total += exp.amount
        is_credit  = (exp.payment_method == 'credit')
        is_project = bool(exp.project_id)
        if is_credit:
            credit_total += exp.amount
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
                'credit_total':  Decimal('0'),
                'project_total': Decimal('0'),
                'office_total':  Decimal('0'),
                'count':         0,
            }
        cat_map[cid]['total']  += exp.amount
        cat_map[cid]['count']  += 1
        if is_credit:
            cat_map[cid]['credit_total'] += exp.amount
        if is_project:
            cat_map[cid]['project_total'] += exp.amount
        else:
            cat_map[cid]['office_total']  += exp.amount

    by_category = sorted(cat_map.values(), key=lambda x: x['total'], reverse=True)
    return total, by_category, rows, project_total, office_total, credit_total


# ── Debt repayment aggregation ────────────────────────────────────────────────

def _debt_payments_in(date_from, date_to):
    """
    Sum of DebtPayment amounts in the period, grouped by payment_source.
    These represent actual cash/bank outflows when debts are being settled.
    Returns (total, rows, by_source_dict).
    """
    qs = DebtPayment.objects.filter(
        payment_date__gte=date_from, payment_date__lte=date_to,
    ).select_related('debt')
    total = _sum_qs(qs, 'amount')
    rows = list(qs.order_by('-payment_date'))
    by_source = {}
    for dp in rows:
        s = dp.payment_source or 'other'
        by_source[s] = by_source.get(s, Decimal('0')) + dp.amount
    return total, rows, by_source


# ── Receivables (Python loop — properties not DB-aggregatable) ───────────────

def _invoice_receivables():
    """Outstanding invoice balances (unpaid / partially paid)."""
    qs = Invoice.objects.exclude(status='cancelled')
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


# ── Period cash-flow by payment method ───────────────────────────────────────

# Shared normaliser (used by both helpers below)
def _norm_method(m):
    m = (m or '').lower()
    if m == 'cash':                    return 'cash'
    if m in ('bank_transfer', 'bank'): return 'bank'
    if m in ('mobile_money', 'mpesa'): return 'mpesa'
    if m == 'cheque':                  return 'cheque'
    return 'other'


def _income_by_method(date_from, date_to):
    """
    All income received in the period, grouped by payment method.
    Sources: InvoicePayment + Invoice.advance_paid + OfficeServicePayment + OfficeIncome(other)
    Returns dict keyed by canonical method ('cash','bank','mpesa','cheque','other').
    """
    D = Decimal
    totals = {k: D('0') for k in ['cash', 'bank', 'mpesa', 'cheque', 'other']}

    for p in InvoicePayment.objects.filter(
            payment_date__gte=date_from, payment_date__lte=date_to,
    ).only('amount', 'payment_method'):
        totals[_norm_method(p.payment_method)] += p.amount

    for inv in Invoice.objects.filter(
            invoice_date__gte=date_from, invoice_date__lte=date_to,
            advance_paid__gt=0,
    ).only('advance_paid', 'advance_payment_method'):
        totals[_norm_method(inv.advance_payment_method)] += inv.advance_paid

    for p in OfficeServicePayment.objects.filter(
            payment_date__gte=date_from, payment_date__lte=date_to,
    ).only('amount', 'payment_method'):
        totals[_norm_method(p.payment_method)] += p.amount

    for inc in OfficeIncome.objects.filter(
            source='other', date__gte=date_from, date__lte=date_to,
    ).only('amount', 'payment_method'):
        totals[_norm_method(inc.payment_method)] += inc.amount

    return {k: float(v) for k, v in totals.items()}


def _outflows_by_method(date_from, date_to):
    """
    All REAL cash/bank outflows in the period, grouped by payment method.
    Sources:
      - Expenses paid via cash/bank/mpesa/cheque (EXCLUDES credit — those create Debt)
      - MaterialOrders paid via cash/bank/mpesa/cheque (credit orders are in AP)
      - DebtPayment — cash actually leaving accounts to settle outstanding debts
    Returns dict keyed by canonical method.
    """
    D = Decimal
    totals = {k: D('0') for k in ['cash', 'bank', 'mpesa', 'cheque', 'other']}

    # Expenses paid immediately (not on credit)
    for exp in Expense.objects.filter(
            date__gte=date_from, date__lte=date_to,
    ).exclude(payment_method='credit').only('amount', 'payment_method'):
        totals[_norm_method(exp.payment_method)] += exp.amount

    for order in MaterialOrder.objects.filter(
            order_date__gte=date_from, order_date__lte=date_to,
            payment_source__in=('cash', 'bank', 'mpesa', 'cheque'),
            status__in=['ordered', 'partially_received', 'received'],
    ).prefetch_related('items'):
        totals[_norm_method(order.payment_source)] += order.total_cost

    for dp in DebtPayment.objects.filter(
            payment_date__gte=date_from, payment_date__lte=date_to,
    ).only('amount', 'payment_source'):
        totals[_norm_method(dp.payment_source)] += dp.amount

    return {k: float(v) for k, v in totals.items()}


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
        adv_income, _, _ = _advance_payments_in(first, last)
        income = inv_income + off_income + oth_income + adv_income

        exp_total, _, _, _, _, credit_exp = _expenses_in(first, last)
        exp_total = exp_total - credit_exp   # cash-only for trend chart

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

    # 4. General expenses paid immediately (exclude credit — those move no cash)
    for exp in Expense.objects.exclude(
        payment_method='credit',
    ).only('amount', 'payment_method'):
        accounts[_norm_out(exp.payment_method)]['out'] += exp.amount

    # 5. Material orders paid via cash/bank/mpesa/cheque (not credit/unspecified)
    paid_sources = ('cash', 'bank', 'mpesa', 'cheque')
    for order in MaterialOrder.objects.filter(
        payment_source__in=paid_sources,
        status__in=['ordered', 'partially_received', 'received'],
    ).prefetch_related('items'):
        accounts[_norm_out(order.payment_source)]['out'] += order.total_cost

    # 6. Debt repayments — cash actually leaving accounts to settle debts
    #    (when payment_source='credit' created a Debt, paying it back IS a cash outflow)
    for dp in DebtPayment.objects.all().only('amount', 'payment_source'):
        accounts[_norm_out(dp.payment_source)]['out'] += dp.amount

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
        for inv in Invoice.objects.exclude(
            status='cancelled'
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
# FOCUSED REPORTS  (AR · AP · Office · Projects · Full)
# ══════════════════════════════════════════════════════════════════════════════

def _method_bucket():
    """Return a fresh dict for tracking amounts by payment method."""
    return {k: Decimal('0') for k in ['cash', 'bank', 'mpesa', 'cheque', 'other']}


def _safe_key(key):
    return key if key in ('cash', 'bank', 'mpesa', 'cheque') else 'other'


def _sync_credit_debts():
    """
    Ensure every credit MaterialOrder and every credit Expense has a
    corresponding Debt record.  Called at the start of compute_ap_report()
    so the AP view is always up-to-date without relying solely on the
    signal-less auto-create in order/expense save paths.

    Uses get_or_create so it is safe to call repeatedly.
    """
    # ── Material orders on credit ──────────────────────────────────────────
    credit_orders = (
        MaterialOrder.objects
        .filter(
            payment_source='credit',
            status__in=['ordered', 'partially_received', 'received'],
        )
        .select_related('project')
        .prefetch_related('items')
    )
    for order in credit_orders:
        Debt.objects.get_or_create(
            material_order=order,
            defaults={
                'creditor_name': order.supplier_name,
                'debt_type':     'supplier_credit',
                'amount':        order.total_cost,
                'date_incurred': order.order_date,
                'description': (
                    f"Materials on credit from {order.supplier_name}"
                    + (f" for project: {order.project.name}" if order.project_id else "")
                ),
                'project': order.project if order.project_id else None,
            },
        )

    # ── Expenses on credit ─────────────────────────────────────────────────
    credit_expenses = (
        Expense.objects
        .filter(payment_method='credit')
        .select_related('category', 'project')
    )
    for exp in credit_expenses:
        Debt.objects.get_or_create(
            expense=exp,
            defaults={
                'creditor_name': exp.paid_to or 'Unknown Creditor',
                'debt_type':     'other',
                'amount':        exp.amount,
                'date_incurred': exp.date,
                'description': (
                    f"{exp.category.name} on credit"
                    + (f" — {exp.description}" if exp.description else "")
                ),
                'project': exp.project if exp.project_id else None,
            },
        )


def compute_ar_report():
    """
    Accounts Receivable — Fedha Tunazodai.
    Returns outstanding balances owed TO the business:
      1. Invoice balances (project clients who haven't paid in full)
      2. Office service balances
    Every row shows how much was received by cash vs bank so far.
    """
    D = Decimal

    # ── Invoice AR ─────────────────────────────────────────────────────────
    # Exclude only cancelled — rely on balance_due > 0 check in Python
    # to catch partial payments regardless of whatever status is set.
    invoices = Invoice.objects.exclude(
        status='cancelled',
    ).prefetch_related('payments', 'projects')

    inv_rows = []
    inv_grand_contract   = D('0')
    inv_grand_received   = D('0')
    inv_grand_outstanding = D('0')
    inv_grand_by_method  = _method_bucket()

    for inv in invoices:
        bal = inv.balance_due
        if bal <= 0:
            continue

        row_by_method = _method_bucket()
        # Advance payment
        k = _safe_key(_norm_method(inv.advance_payment_method))
        row_by_method[k]       += inv.advance_paid
        inv_grand_by_method[k] += inv.advance_paid
        # Instalment payments
        for p in inv.payments.all():
            k = _safe_key(_norm_method(p.payment_method))
            row_by_method[k]       += p.amount
            inv_grand_by_method[k] += p.amount

        inv_grand_contract    += inv.contract_amount
        inv_grand_received    += inv.total_paid
        inv_grand_outstanding += bal

        proj = inv.projects.first()
        inv_rows.append({
            'pk':               inv.pk,
            'invoice_no':       inv.invoice_no,
            'client_name':      inv.client_name,
            'client_phone':     inv.client_phone,
            'project_name':     proj.name if proj else '—',
            'project_pk':       proj.pk   if proj else None,
            'invoice_date':     inv.invoice_date,
            'due_date':         inv.due_date,
            'contract_amount':  float(inv.contract_amount),
            'total_received':   float(inv.total_paid),
            'balance':          float(bal),
            'is_overdue':       inv.is_overdue,
            'recv_cash':        float(row_by_method['cash']),
            'recv_bank':        float(row_by_method['bank']),
            'recv_mpesa':       float(row_by_method['mpesa']),
            'recv_cheque':      float(row_by_method['cheque']),
            'recv_other':       float(row_by_method['other']),
        })

    inv_rows.sort(key=lambda r: (not r['is_overdue'], r['due_date'] or date.max))

    # ── Office Service AR ───────────────────────────────────────────────────
    svc_records = OfficeServiceRecord.objects.exclude(
        status='paid'
    ).prefetch_related('payments').order_by('-date_recorded')

    svc_rows = []
    svc_grand_charge      = D('0')
    svc_grand_received    = D('0')
    svc_grand_outstanding = D('0')
    svc_grand_by_method   = _method_bucket()

    for rec in svc_records:
        bal = rec.balance
        if bal <= 0:
            continue

        row_by_method = _method_bucket()
        for p in rec.payments.all():
            k = _safe_key(_norm_method(p.payment_method))
            row_by_method[k]        += p.amount
            svc_grand_by_method[k]  += p.amount

        svc_grand_charge      += rec.total_charge
        svc_grand_received    += rec.total_paid
        svc_grand_outstanding += bal

        svc_rows.append({
            'pk':               rec.pk,
            'client_name':      rec.client_name,
            'client_phone':     rec.client_phone,
            'work_description': rec.work_description,
            'num_windows':      rec.num_windows,
            'num_doors':        rec.num_doors,
            'date_recorded':    rec.date_recorded,
            'due_date':         rec.due_date,
            'total_charge':     float(rec.total_charge),
            'total_received':   float(rec.total_paid),
            'balance':          float(bal),
            'is_overdue':       rec.is_overdue,
            'recv_cash':        float(row_by_method['cash']),
            'recv_bank':        float(row_by_method['bank']),
            'recv_mpesa':       float(row_by_method['mpesa']),
            'recv_other':       float(row_by_method['cheque'] + row_by_method['other']),
        })

    svc_rows.sort(key=lambda r: (not r['is_overdue'], r['due_date'] or date.max))

    # ── Combined list (invoices + services, overdue first) ──────────────────
    all_rows = []
    for r in inv_rows:
        all_rows.append({
            'type':           'invoice',
            'pk':             r['pk'],
            'client_name':    r['client_name'],
            'client_phone':   r['client_phone'],
            'ref':            r['invoice_no'],
            'sub_ref':        r['project_name'] if r['project_name'] != '—' else None,
            'sub_ref_pk':     r['project_pk'],
            'date':           r['invoice_date'],
            'due_date':       r['due_date'],
            'total_charged':  r['contract_amount'],
            'total_received': r['total_received'],
            'balance':        r['balance'],
            'is_overdue':     r['is_overdue'],
            'recv_cash':      r['recv_cash'],
            'recv_bank':      r['recv_bank'],
            'recv_mpesa':     r['recv_mpesa'],
            'recv_other':     r['recv_other'],
        })
    for r in svc_rows:
        all_rows.append({
            'type':           'service',
            'pk':             r['pk'],
            'client_name':    r['client_name'],
            'client_phone':   r['client_phone'],
            'ref':            r['work_description'],
            'sub_ref':        f"{r['num_windows']}W/{r['num_doors']}D" if (r['num_windows'] or r['num_doors']) else None,
            'sub_ref_pk':     None,
            'date':           r['date_recorded'],
            'due_date':       r['due_date'],
            'total_charged':  r['total_charge'],
            'total_received': r['total_received'],
            'balance':        r['balance'],
            'is_overdue':     r['is_overdue'],
            'recv_cash':      r['recv_cash'],
            'recv_bank':      r['recv_bank'],
            'recv_mpesa':     r['recv_mpesa'],
            'recv_other':     r['recv_other'],
        })
    all_rows.sort(key=lambda r: (not r['is_overdue'], r['due_date'] or date.max))

    return {
        # Invoice receivables
        'inv_rows':              inv_rows,
        'inv_total_contract':    float(inv_grand_contract),
        'inv_total_received':    float(inv_grand_received),
        'inv_total_outstanding': float(inv_grand_outstanding),
        'inv_recv_cash':         float(inv_grand_by_method['cash']),
        'inv_recv_bank':         float(inv_grand_by_method['bank']),
        'inv_recv_mpesa':        float(inv_grand_by_method['mpesa']),
        'inv_recv_other':        float(inv_grand_by_method['cheque'] + inv_grand_by_method['other']),
        # Office service receivables
        'svc_rows':              svc_rows,
        'svc_total_charge':      float(svc_grand_charge),
        'svc_total_received':    float(svc_grand_received),
        'svc_total_outstanding': float(svc_grand_outstanding),
        'svc_recv_cash':         float(svc_grand_by_method['cash']),
        'svc_recv_bank':         float(svc_grand_by_method['bank']),
        'svc_recv_mpesa':        float(svc_grand_by_method['mpesa']),
        'svc_recv_other':        float(svc_grand_by_method['cheque'] + svc_grand_by_method['other']),
        # Grand total
        'total_ar': float(inv_grand_outstanding + svc_grand_outstanding),
        # Combined single list
        'all_rows': all_rows,
        'total_recv_cash':  float(inv_grand_by_method['cash']  + svc_grand_by_method['cash']),
        'total_recv_bank':  float(inv_grand_by_method['bank']  + svc_grand_by_method['bank']),
        'total_recv_mpesa': float(inv_grand_by_method['mpesa'] + svc_grand_by_method['mpesa']),
    }


def compute_ap_report():
    """
    Accounts Payable — Madeni Yetu.
    Returns outstanding balances owed BY the business (unsettled debts).
    Grouped by debt type (supplier credit, labour credit, loans…).
    Each row shows how much has been repaid by cash vs bank.
    Includes context from linked material orders and credit expenses.
    """
    # Ensure all credit orders/expenses have a Debt record before querying
    _sync_credit_debts()

    debts = Debt.objects.exclude(status='settled').select_related(
        'project', 'material_order', 'expense', 'expense__category',
    ).prefetch_related('payments', 'material_order__items').order_by('due_date', '-date_incurred')

    grand_original    = Decimal('0')
    grand_repaid      = Decimal('0')
    grand_outstanding = Decimal('0')
    grand_repaid_by   = _method_bucket()
    by_type           = {}   # key → {label, rows, totals…}

    for d in debts:
        bal = d.balance
        row_repaid = _method_bucket()
        for p in d.payments.all():
            k = _safe_key(_norm_method(p.payment_source))
            row_repaid[k]       += p.amount
            grand_repaid_by[k]  += p.amount

        grand_original    += d.amount
        grand_repaid      += d.total_paid
        grand_outstanding += bal

        dtype = d.debt_type
        if dtype not in by_type:
            by_type[dtype] = {
                'label':            d.get_debt_type_display(),
                'rows':             [],
                'total_original':   Decimal('0'),
                'total_repaid':     Decimal('0'),
                'total_outstanding': Decimal('0'),
                'repaid_cash':      Decimal('0'),
                'repaid_bank':      Decimal('0'),
                'repaid_mpesa':     Decimal('0'),
                'repaid_other':     Decimal('0'),
            }
        g = by_type[dtype]
        g['total_original']    += d.amount
        g['total_repaid']      += d.total_paid
        g['total_outstanding'] += bal
        g['repaid_cash']       += row_repaid['cash']
        g['repaid_bank']       += row_repaid['bank']
        g['repaid_mpesa']      += row_repaid['mpesa']
        g['repaid_other']      += row_repaid['cheque'] + row_repaid['other']

        # Material order context (credit purchase)
        order_ctx = None
        if d.material_order_id:
            o = d.material_order
            order_ctx = {
                'pk':        o.pk,
                'supplier':  o.supplier_name,
                'date':      o.order_date,
                'status':    o.get_status_display(),
                'items_count': o.items.count(),
                'total':     float(o.total_cost),
            }

        # Expense context (credit expense)
        expense_ctx = None
        if d.expense_id:
            e = d.expense
            expense_ctx = {
                'pk':          e.pk,
                'category':    e.category.name,
                'description': e.description,
                'date':        e.date,
                'paid_to':     e.paid_to,
            }

        # Determine source type for display
        if order_ctx:
            source_type = 'material_order'
        elif expense_ctx:
            source_type = 'expense'
        else:
            source_type = 'manual'

        g['rows'].append({
            'pk':              d.pk,
            'creditor_name':   d.creditor_name,
            'creditor_phone':  d.creditor_phone,
            'description':     d.description,
            'date_incurred':   d.date_incurred,
            'due_date':        d.due_date,
            'original_amount': float(d.amount),
            'total_repaid':    float(d.total_paid),
            'balance':         float(bal),
            'is_overdue':      d.is_overdue,
            'repaid_cash':     float(row_repaid['cash']),
            'repaid_bank':     float(row_repaid['bank']),
            'repaid_mpesa':    float(row_repaid['mpesa']),
            'repaid_other':    float(row_repaid['cheque'] + row_repaid['other']),
            'project_name':    d.project.name if d.project_id else None,
            'project_pk':      d.project_id,
            'source_type':     source_type,
            'order_ctx':       order_ctx,
            'expense_ctx':     expense_ctx,
        })

    # Serialise by_type for the template
    type_sections = [
        {
            'type':              k,
            'label':             v['label'],
            'rows':              v['rows'],
            'total_original':    float(v['total_original']),
            'total_repaid':      float(v['total_repaid']),
            'total_outstanding': float(v['total_outstanding']),
            'repaid_cash':       float(v['repaid_cash']),
            'repaid_bank':       float(v['repaid_bank']),
            'repaid_mpesa':      float(v['repaid_mpesa']),
            'repaid_other':      float(v['repaid_other']),
        }
        for k, v in by_type.items()
    ]

    return {
        'type_sections':    type_sections,
        'total_original':   float(grand_original),
        'total_repaid':     float(grand_repaid),
        'total_outstanding': float(grand_outstanding),
        'repaid_cash':      float(grand_repaid_by['cash']),
        'repaid_bank':      float(grand_repaid_by['bank']),
        'repaid_mpesa':     float(grand_repaid_by['mpesa']),
        'repaid_other':     float(grand_repaid_by['cheque'] + grand_repaid_by['other']),
    }


def compute_office_report():
    """
    Office Services — all records (pending, partial, paid).
    Shows per-client breakdown and cash vs bank payment totals.
    """
    records = OfficeServiceRecord.objects.prefetch_related(
        'payments'
    ).order_by('-date_recorded')

    rows = []
    grand_charged      = Decimal('0')
    grand_received     = Decimal('0')
    grand_outstanding  = Decimal('0')
    grand_by_method    = _method_bucket()

    for rec in records:
        charge = rec.total_charge
        paid   = rec.total_paid
        bal    = rec.balance

        row_by = _method_bucket()
        for p in rec.payments.all():
            k = _safe_key(_norm_method(p.payment_method))
            row_by[k]            += p.amount
            grand_by_method[k]   += p.amount

        grand_charged     += charge
        grand_received    += paid
        grand_outstanding += bal

        rows.append({
            'pk':               rec.pk,
            'client_name':      rec.client_name,
            'client_phone':     rec.client_phone,
            'work_description': rec.work_description,
            'num_windows':      rec.num_windows,
            'num_doors':        rec.num_doors,
            'date_recorded':    rec.date_recorded,
            'due_date':         rec.due_date,
            'status':           rec.status,
            'status_display':   rec.get_status_display(),
            'total_charge':     float(charge),
            'total_paid':       float(paid),
            'balance':          float(bal),
            'is_overdue':       rec.is_overdue,
            'paid_cash':        float(row_by['cash']),
            'paid_bank':        float(row_by['bank']),
            'paid_mpesa':       float(row_by['mpesa']),
            'paid_other':       float(row_by['cheque'] + row_by['other']),
        })

    return {
        'rows':               rows,
        'total_charged':      float(grand_charged),
        'total_received':     float(grand_received),
        'total_outstanding':  float(grand_outstanding),
        'received_cash':      float(grand_by_method['cash']),
        'received_bank':      float(grand_by_method['bank']),
        'received_mpesa':     float(grand_by_method['mpesa']),
        'received_other':     float(grand_by_method['cheque'] + grand_by_method['other']),
    }


def compute_projects_report():
    """
    All non-cancelled projects — individual + accumulative.
    Revenue tracked by payment method (cash/bank/mpesa).
    Shows cost breakdown (materials + direct expenses) and profit margin.
    """
    projects = Project.objects.select_related(
        'invoice',
    ).prefetch_related(
        'orders', 'expenses', 'invoice__payments',
    ).exclude(status='cancelled').order_by('-created_at')

    rows             = []
    grand_revenue    = Decimal('0')
    grand_materials  = Decimal('0')
    grand_expenses   = Decimal('0')
    grand_profit     = Decimal('0')
    grand_rev_by     = _method_bucket()
    grand_received   = Decimal('0')
    grand_outstanding = Decimal('0')

    for p in projects:
        rev  = p.revenue
        mat  = p.materials_cost
        exp  = p.direct_expenses_cost
        prof = rev - mat - exp

        grand_revenue   += rev
        grand_materials += mat
        grand_expenses  += exp
        grand_profit    += prof

        # Revenue collected by method
        row_rev_by = _method_bucket()
        received   = Decimal('0')
        if p.invoice_id:
            inv = p.invoice
            k   = _safe_key(_norm_method(inv.advance_payment_method))
            row_rev_by[k]   += inv.advance_paid
            grand_rev_by[k] += inv.advance_paid
            received        += inv.advance_paid
            for pmt in inv.payments.all():
                k = _safe_key(_norm_method(pmt.payment_method))
                row_rev_by[k]   += pmt.amount
                grand_rev_by[k] += pmt.amount
                received        += pmt.amount
            outstanding = inv.balance_due
        else:
            outstanding = rev   # not invoiced yet → full amount outstanding

        grand_received    += received
        grand_outstanding += outstanding

        rows.append({
            'pk':              p.pk,
            'name':            p.name,
            'client_name':     p.client_name,
            'status':          p.status,
            'status_display':  p.get_status_display(),
            'start_date':      p.start_date,
            'completion_date': p.completion_date,
            'revenue':         float(rev),
            'materials_cost':  float(mat),
            'expenses_cost':   float(exp),
            'total_cost':      float(mat + exp),
            'gross_profit':    float(prof),
            'profit_margin':   float(p.profit_margin),
            'rev_cash':        float(row_rev_by['cash']),
            'rev_bank':        float(row_rev_by['bank']),
            'rev_mpesa':       float(row_rev_by['mpesa']),
            'rev_other':       float(row_rev_by['cheque'] + row_rev_by['other']),
            'rev_received':    float(received),
            'rev_outstanding': float(outstanding),
            'has_invoice':     bool(p.invoice_id),
            'invoice_no':      p.invoice.invoice_no if p.invoice_id else None,
        })

    margin = (grand_profit / grand_revenue * 100) if grand_revenue > 0 else Decimal('0')

    return {
        'rows':              rows,
        'total_revenue':     float(grand_revenue),
        'total_materials':   float(grand_materials),
        'total_expenses':    float(grand_expenses),
        'total_cost':        float(grand_materials + grand_expenses),
        'total_profit':      float(grand_profit),
        'profit_margin':     float(margin),
        'total_received':    float(grand_received),
        'total_outstanding': float(grand_outstanding),
        'rev_cash':          float(grand_rev_by['cash']),
        'rev_bank':          float(grand_rev_by['bank']),
        'rev_mpesa':         float(grand_rev_by['mpesa']),
        'rev_other':         float(grand_rev_by['cheque'] + grand_rev_by['other']),
    }


def _income_ledger(date_from, date_to):
    """
    Every individual income transaction in the period, sorted by date descending.
    Sources: InvoicePayment, Invoice advance payments, OfficeServicePayment, OfficeIncome.
    Returns {'rows': [...], 'total': float, 'by_method': {method: float}}.
    """
    rows = []

    # 1. Invoice instalment payments
    for p in InvoicePayment.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to,
    ).select_related('invoice').order_by('-payment_date'):
        rows.append({
            'date':        p.payment_date,
            'source_type': 'invoice_payment',
            'icon':        'bi-receipt-cutoff',
            'badge_class': 'bg-primary',
            'label':       'Invoice',
            'client_name': p.invoice.client_name if p.invoice else '—',
            'ref':         p.invoice.invoice_no if p.invoice else '—',
            'description': f"Invoice payment — {p.invoice.invoice_no}" if p.invoice else 'Invoice payment',
            'amount':      p.amount,
            'method':      _norm_method(p.payment_method),
            'pk':          p.invoice.pk if p.invoice else None,
        })

    # 2. Advance payments on invoices
    for inv in Invoice.objects.filter(
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
        advance_paid__gt=0,
    ).only('invoice_no', 'client_name', 'advance_paid', 'advance_payment_method', 'invoice_date', 'id'):
        rows.append({
            'date':        inv.invoice_date,
            'source_type': 'advance',
            'icon':        'bi-cash',
            'badge_class': 'bg-success',
            'label':       'Advance',
            'client_name': inv.client_name,
            'ref':         inv.invoice_no,
            'description': f"Advance payment — {inv.invoice_no}",
            'amount':      inv.advance_paid,
            'method':      _norm_method(inv.advance_payment_method),
            'pk':          inv.pk,
        })

    # 3. Office service payments
    for p in OfficeServicePayment.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to,
    ).select_related('record').order_by('-payment_date'):
        rows.append({
            'date':        p.payment_date,
            'source_type': 'office_payment',
            'icon':        'bi-building',
            'badge_class': 'bg-info text-dark',
            'label':       'Office Svc',
            'client_name': p.record.client_name if p.record else '—',
            'ref':         '—',
            'description': (p.record.work_description[:40] if p.record and p.record.work_description else 'Office service'),
            'amount':      p.amount,
            'method':      _norm_method(p.payment_method),
            'pk':          p.record.pk if p.record else None,
        })

    # 4. Other income (OfficeIncome with source='other')
    for inc in OfficeIncome.objects.filter(
        source='other',
        date__gte=date_from,
        date__lte=date_to,
    ):
        rows.append({
            'date':        inc.date,
            'source_type': 'other_income',
            'icon':        'bi-three-dots',
            'badge_class': 'bg-secondary',
            'label':       'Other',
            'client_name': '—',
            'ref':         '—',
            'description': inc.description or 'Other income',
            'amount':      inc.amount,
            'method':      _norm_method(inc.payment_method),
            'pk':          None,
        })

    rows.sort(key=lambda r: r['date'], reverse=True)

    total = sum(r['amount'] for r in rows)
    by_method = {}
    for r in rows:
        m = r['method']
        by_method[m] = by_method.get(m, Decimal('0')) + r['amount']

    return {
        'rows':      rows,
        'total':     float(total),
        'by_method': {k: float(v) for k, v in by_method.items()},
        'count':     len(rows),
    }


def compute_full_report(date_from, date_to):
    """
    Full combined report for a period:
      - Cash/Bank account balance (all-time)
      - AR summary
      - AP summary
      - Period income + expenses broken down by cash/bank
    """
    # Period income & expenses by method
    inc_by  = _income_by_method(date_from, date_to)
    out_by  = _outflows_by_method(date_from, date_to)

    METHOD_LABELS = {
        'cash':   ('Cash (Fedha Taslimu)', 'bi-cash-coin',  '#16a34a'),
        'bank':   ('Bank Transfer',        'bi-bank',       '#2563eb'),
        'mpesa':  ('M-Pesa / Mobile',      'bi-phone',      '#059669'),
        'cheque': ('Cheque',               'bi-file-text',  '#7c3aed'),
        'other':  ('Nyingine',             'bi-three-dots', '#94a3b8'),
    }
    cashflow_by_method = []
    for key in ['cash', 'bank', 'mpesa', 'cheque', 'other']:
        i = inc_by.get(key, 0)
        o = out_by.get(key, 0)
        if i == 0 and o == 0:
            continue
        lbl, icon, color = METHOD_LABELS[key]
        cashflow_by_method.append({
            'key': key, 'label': lbl, 'icon': icon, 'color': color,
            'in': i, 'out': o, 'net': i - o,
        })

    # ── Totals from cash-flow view (real money moved) ─────────────────────
    total_cash_in  = sum(inc_by.values())   # actual cash/bank received (float)
    total_cash_out = sum(out_by.values())   # actual cash/bank paid out (float)
    net_cash_flow  = total_cash_in - total_cash_out

    # ── Expenses breakdown ────────────────────────────────────────────────
    exp_total, by_category, _, proj_exp_total, office_exp_total, credit_exp_total = _expenses_in(date_from, date_to)
    cash_exp_total = exp_total - credit_exp_total  # Decimal (cash-only, no credit)
    # Keep a float version to avoid Decimal/float mixing in arithmetic below
    cash_exp_total_f = float(cash_exp_total)

    # ── AR & AP summaries (all-time outstanding) ───────────────────────────
    ar = compute_ar_report()
    ap = compute_ap_report()

    # ── All-time funds position ────────────────────────────────────────────
    funds = _funds_position()

    # ── Period income sources (for breakdown cards) ────────────────────────
    inv_income, _ = _invoice_payments_in(date_from, date_to)
    off_income, _ = _office_payments_in(date_from, date_to)
    oth_income, _ = _other_income_in(date_from, date_to)
    adv_income, _, _ = _advance_payments_in(date_from, date_to)

    debt_pmt_total, _, _ = _debt_payments_in(date_from, date_to)

    # ── Income ledger — every transaction line in the period ───────────────
    ledger = _income_ledger(date_from, date_to)

    return {
        'date_from':          str(date_from),
        'date_to':            str(date_to),
        # ── Cash Flow view (real money moved this period) ─────────────────
        'total_income':       total_cash_in,       # cash/bank actually received
        'total_cash_out':     total_cash_out,       # cash/bank actually paid out
        'net_cash_flow':      net_cash_flow,        # cash in - cash out
        # ── P&L view (expenses when incurred, not when paid) ─────────────
        'total_pl_expenses':  float(exp_total),     # all expenses incl. credit
        'cash_expenses':      cash_exp_total_f,       # cash-only expenses (no credit)
        'net_profit':         total_cash_in - cash_exp_total_f,  # float - float
        # ── Income breakdown ──────────────────────────────────────────────
        'invoice_income':     float(inv_income),
        'advance_income':     float(adv_income),
        'office_income':      float(off_income),
        'other_income':       float(oth_income),
        # ── Expense breakdown ─────────────────────────────────────────────
        'project_expenses_total': float(proj_exp_total),
        'office_expenses_total':  float(office_exp_total),
        'debt_payments_total':    float(debt_pmt_total),
        'credit_exp_total':       float(credit_exp_total),  # new debts (no cash)
        'by_category':            by_category,
        # ── Cash flow by account for the period ───────────────────────────
        'cashflow_by_method': cashflow_by_method,
        # ── AR & AP (all-time outstanding) ────────────────────────────────
        'ar_total':           ar['total_ar'],
        'ar_inv_outstanding': ar['inv_total_outstanding'],
        'ar_svc_outstanding': ar['svc_total_outstanding'],
        'ap_total':           ap['total_outstanding'],
        # ── Funds position (all-time balance sheet) ───────────────────────
        'funds':              funds,
        # ── Income ledger (every payment received in period) ──────────────
        'income_ledger':      ledger,
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

    exp_total, by_category, exp_rows, proj_exp_total, office_exp_total, credit_exp_total = _expenses_in(today, today)
    cash_exp_total = exp_total - credit_exp_total  # only expenses paid in cash/bank
    debt_pmt_total, debt_pmt_rows, debt_pmt_by_source = _debt_payments_in(today, today)
    total_out = cash_exp_total + debt_pmt_total    # real cash leaving accounts
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
        'total_in':  total_in,
        'total_out': total_out,          # cash-only: excludes credit expenses
        'exp_total': cash_exp_total,     # cash expenses only (for "money out" display)
        'credit_exp_total': credit_exp_total,  # new debts recorded today (no cash)
        'net_today': total_in - total_out,
        # Breakdown of inflows
        'invoice_income': inv_income,
        'advance_income': adv_income,
        'advance_rows':   adv_rows,
        'office_income':  off_income,
        'other_income':   oth_income,
        'inv_payments':   inv_payments,
        'off_payments':   off_payments,
        # Expenses today (ALL including credit — template marks credit rows)
        'expenses': exp_rows,
        'by_category': by_category,
        'project_expenses_total': proj_exp_total,
        'office_expenses_total':  office_exp_total,
        # Debt repayments today (real cash leaving the account)
        'debt_payments': debt_pmt_rows,
        'debt_payments_total': debt_pmt_total,
        'debt_payments_by_source': debt_pmt_by_source,
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
    total_expenses, by_category, expense_rows, proj_exp_total, office_exp_total, credit_exp_total = _expenses_in(date_from, date_to)
    cash_expenses = total_expenses - credit_exp_total  # actual cash paid

    # ── Debt repayments in period ─────────────────────────────────────────────
    debt_pmt_total, debt_pmt_rows, debt_pmt_by_source = _debt_payments_in(date_from, date_to)

    # ── Net ───────────────────────────────────────────────────────────────────
    # net_profit = cash income minus cash expenses (consistent cash-basis)
    net_profit = total_income - cash_expenses
    # net_cash_flow = income minus all cash outflows including debt repayments
    net_cash_flow = total_income - cash_expenses - debt_pmt_total

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

    # ── Period cash-flow by method ────────────────────────────────────────────
    income_by_method   = _income_by_method(date_from, date_to)
    outflows_by_method = _outflows_by_method(date_from, date_to)
    _METHOD_LABELS = {
        'cash':   ('Cash (Fedha Taslimu)', 'bi-cash-coin',  '#16a34a'),
        'bank':   ('Bank Transfer',        'bi-bank',       '#2563eb'),
        'mpesa':  ('M-Pesa / Mobile',      'bi-phone',      '#059669'),
        'cheque': ('Cheque',               'bi-file-text',  '#7c3aed'),
        'other':  ('Nyingine',             'bi-three-dots', '#94a3b8'),
    }
    cashflow_by_method = []
    for key in ['cash', 'bank', 'mpesa', 'cheque', 'other']:
        inc  = income_by_method.get(key, 0)
        out  = outflows_by_method.get(key, 0)
        if inc == 0 and out == 0:
            continue
        lbl, icon, color = _METHOD_LABELS[key]
        cashflow_by_method.append({
            'key': key, 'label': lbl, 'icon': icon, 'color': color,
            'in': inc, 'out': out, 'net': inc - out,
        })

    # ── Alerts ────────────────────────────────────────────────────────────────
    alerts = _build_alerts(
        inv_ov_c, inv_ov_a, svc_ov_c, svc_ov_a, by_category, total_expenses,
        debt_overdue_count=liabilities['overdue_count'],
        debt_overdue_amount=liabilities['overdue_amount'],
    )

    # ── Income breakdown (only non-zero sources) ──────────────────────────────
    income_breakdown = [
        row for row in [
            {'source': 'Malipo ya Invoice (Instalments)', 'amount': float(inv_income)},
            {'source': 'Malipo ya Awali (Advances)',       'amount': float(adv_income)},
            {'source': 'Huduma za Ofisi (Office Services)', 'amount': float(off_income)},
            {'source': 'Mapato Mengine (Other)',             'amount': float(oth_income)},
        ]
        if row['amount'] > 0
    ]

    return {
        # Summary
        'date_from': str(date_from),
        'date_to': str(date_to),
        'total_income': float(total_income),
        'total_expenses': float(total_expenses),
        'debt_payments_total': float(debt_pmt_total),
        'net_profit': float(net_profit),
        'net_cash_flow': float(net_cash_flow),
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
                'credit_total':  float(c['credit_total']),
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

        # Debt repayments in period (cash outflows for settling debts)
        'debt_payments_by_source': {k: float(v) for k, v in debt_pmt_by_source.items()},
        'debt_payment_rows': [
            {
                'creditor_name':  dp.debt.creditor_name,
                'debt_type':      dp.debt.get_debt_type_display(),
                'amount':         float(dp.amount),
                'payment_date':   str(dp.payment_date),
                'payment_source': dp.payment_source,
                'reference':      dp.reference,
            }
            for dp in debt_pmt_rows
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

        # Period cash-flow by method
        'income_by_method':   income_by_method,
        'outflows_by_method': outflows_by_method,
        'cashflow_by_method': cashflow_by_method,

        # Trends
        'monthly_trends': trends,

        # Liabilities
        'liabilities': liabilities,

        # Funds position (all-time: where is the money)
        'funds': funds,

        # Alerts
        'alerts': alerts,
    }
