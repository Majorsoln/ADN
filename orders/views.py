import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST

from projects.models import Project, ProjectEvent
from .models import MaterialOrder, MaterialOrderItem
from .forms import MaterialOrderForm
from accounts.decorators import login_required, editor_required, admin_required


def _log(project, event_type, description):
    ProjectEvent.objects.create(project=project, event_type=event_type, description=description)


@login_required
def list_view(request):
    """All material orders across all projects."""
    qs = MaterialOrder.objects.select_related('project').prefetch_related('items')

    status_filter = request.GET.get('status', '')
    search        = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(supplier_name__icontains=search) | qs.filter(project__name__icontains=search)

    # Summary counts
    totals = {s: 0 for s, _ in MaterialOrder.STATUS_CHOICES}
    for o in MaterialOrder.objects.all():
        totals[o.status] = totals.get(o.status, 0) + 1

    return render(request, 'orders/list.html', {
        'orders':        qs,
        'status_filter': status_filter,
        'search':        search,
        'status_choices': MaterialOrder.STATUS_CHOICES,
        'totals':        totals,
        'today':         timezone.now().date(),
    })


def _save_items(order, items_json):
    """Parse JSON and create MaterialOrderItem rows."""
    try:
        items = json.loads(items_json)
        for i, item in enumerate(items):
            if item.get('material_name') and item.get('quantity') and item.get('unit_cost'):
                MaterialOrderItem.objects.create(
                    order=order,
                    material_name=item['material_name'],
                    description=item.get('description', ''),
                    quantity=Decimal(str(item['quantity'])),
                    unit=item.get('unit', 'm2'),
                    unit_cost=Decimal(str(item['unit_cost'])),
                    order_index=i,
                )
    except Exception:
        pass


@editor_required
def create_view(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if request.method == 'POST':
        form = MaterialOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.project = project
            order.save()
            _save_items(order, request.POST.get('items_data', '[]'))

            item_count = order.items.count()
            _log(project, 'order_new',
                 f'Material order created: {order.supplier_name} '
                 f'({item_count} item{"s" if item_count != 1 else ""}, '
                 f'TZS {order.total_cost:,.0f}) — status: {order.get_status_display()}')

            # Advance project from planning → ordered when first order is finalised
            if order.status != 'draft' and project.status == 'planning':
                project.status = 'ordered'
                project.save(update_fields=['status'])
                _log(project, 'status', 'Status changed: Planning → Materials Ordered')

            # Auto-create debt if created directly as "ordered" on credit
            if order.status == 'ordered' and order.payment_source == 'credit':
                from finance.models import Debt
                Debt.objects.get_or_create(
                    material_order=order,
                    defaults={
                        'creditor_name': order.supplier_name,
                        'debt_type':     'supplier_credit',
                        'amount':        order.total_cost,
                        'date_incurred': order.order_date,
                        'description':   (
                            f"Materials on credit from {order.supplier_name} "
                            f"for project: {project.name}"
                        ),
                        'project': project,
                    }
                )
                _log(project, 'order_new',
                     f'Debt auto-created: TZS {order.total_cost:,.0f} owed to '
                     f'{order.supplier_name} (credit purchase)')

            messages.success(request, f'Order from {order.supplier_name} created.')
            return redirect('projects:detail', pk=project_pk)
    else:
        form = MaterialOrderForm()
    return render(request, 'orders/form.html', {'form': form, 'project': project, 'action': 'Create'})


@login_required
def detail_view(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    return render(request, 'orders/detail.html', {'order': order})


@editor_required
def edit_view(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    old_status = order.status
    old_payment_source = order.payment_source
    if request.method == 'POST':
        form = MaterialOrderForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save()

            # Safe item replacement: parse first, only replace if we have valid items
            items_data = request.POST.get('items_data', '[]')
            try:
                parsed_items = json.loads(items_data)
                valid_items = [i for i in parsed_items if i.get('material_name') and i.get('quantity') and i.get('unit_cost')]
            except (json.JSONDecodeError, ValueError):
                valid_items = []

            if valid_items:
                order.items.all().delete()
                _save_items(order, json.dumps(valid_items))
            # else: keep existing items untouched — don't silently delete them

            desc = f'Order from {order.supplier_name} edited — {order.items.count()} items, TZS {order.total_cost:,.0f}'
            if order.status != old_status:
                desc += f' (status: {dict(MaterialOrder.STATUS_CHOICES).get(old_status)} → {order.get_status_display()})'
            _log(order.project, 'order_edit', desc)

            # Advance project if order just became non-draft
            if old_status == 'draft' and order.status != 'draft' and order.project.status == 'planning':
                order.project.status = 'ordered'
                order.project.save(update_fields=['status'])
                _log(order.project, 'status', 'Status changed: Planning → Materials Ordered')

            # Auto-create or update Debt if now ordered on credit
            if order.status == 'ordered' and order.payment_source == 'credit':
                from finance.models import Debt
                debt, created = Debt.objects.get_or_create(
                    material_order=order,
                    defaults={
                        'creditor_name': order.supplier_name,
                        'debt_type':     'supplier_credit',
                        'amount':        order.total_cost,
                        'date_incurred': order.order_date,
                        'description':   (
                            f"Materials on credit from {order.supplier_name} "
                            f"for project: {order.project.name}"
                        ),
                        'project': order.project,
                    }
                )
                if not created and debt.amount != order.total_cost:
                    debt.amount = order.total_cost
                    debt.save(update_fields=['amount'])
                if created:
                    _log(order.project, 'order_edit',
                         f'Debt auto-created: TZS {order.total_cost:,.0f} owed to '
                         f'{order.supplier_name} (credit purchase)')

            # Auto-advance project to in_progress if first delivery received
            if order.status == 'received' and old_status != 'received' and order.project.status == 'ordered':
                order.project.status = 'in_progress'
                order.project.save(update_fields=['status'])
                _log(order.project, 'status',
                     'Status changed: Materials Ordered → In Progress (delivery received)')

            messages.success(request, 'Order updated.')
            return redirect('projects:detail', pk=order.project.pk)
    else:
        form = MaterialOrderForm(instance=order)
    existing_items = list(order.items.values('material_name', 'description', 'quantity', 'unit', 'unit_cost'))
    return render(request, 'orders/form.html', {
        'form': form, 'order': order,
        'project': order.project,
        'existing_items': existing_items,
        'action': 'Edit',
    })


@admin_required
def delete_view(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    project_pk = order.project.pk
    if request.method == 'POST':
        _log(order.project, 'order_del',
             f'Order from {order.supplier_name} deleted '
             f'(was {order.get_status_display()}, TZS {order.total_cost:,.0f}).')
        order.delete()
        messages.success(request, 'Order deleted.')
        return redirect('projects:detail', pk=project_pk)
    return render(request, 'orders/confirm_delete.html', {'order': order})


@editor_required
@require_POST
def update_status(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in MaterialOrder.STATUS_CHOICES]
    if new_status in valid and new_status != order.status:
        old_label = order.get_status_display()
        order.status = new_status
        # Capture payment_source when order is being finalized (draft → ordered)
        payment_source = request.POST.get('payment_source', '')
        valid_sources = [c[0] for c in MaterialOrder.PAYMENT_SOURCE_CHOICES]
        if payment_source in valid_sources:
            order.payment_source = payment_source
        if new_status == 'received':
            order.actual_delivery = timezone.now().date()
        order.save()

        # Auto-create a Debt record when materials are bought on credit
        if payment_source == 'credit' and new_status == 'ordered':
            from finance.models import Debt
            Debt.objects.get_or_create(
                material_order=order,
                defaults={
                    'creditor_name': order.supplier_name,
                    'debt_type':     'supplier_credit',
                    'amount':        order.total_cost,
                    'date_incurred': order.order_date,
                    'description':   (
                        f"Materials on credit from {order.supplier_name} "
                        f"for project: {order.project.name}"
                    ),
                    'project': order.project,
                }
            )
            _log(order.project, 'order_status',
                 f'Debt auto-created: TZS {order.total_cost:,.0f} owed to '
                 f'{order.supplier_name} (credit purchase)')

        new_label = order.get_status_display()
        _log(order.project, 'order_status',
             f'Order ({order.supplier_name}) status: {old_label} → {new_label}')

        # Auto-advance project to in_progress when any order is received
        if new_status == 'received' and order.project.status == 'ordered':
            order.project.status = 'in_progress'
            order.project.save(update_fields=['status'])
            _log(order.project, 'status',
                 'Status changed: Materials Ordered → In Progress (first delivery received)')

        messages.success(request, f'Order status updated to {new_label}.')
    return redirect('orders:detail', pk=pk)
