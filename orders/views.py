import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST

from projects.models import Project, ProjectEvent
from .models import MaterialOrder, MaterialOrderItem
from .forms import MaterialOrderForm


def _log(project, event_type, description):
    ProjectEvent.objects.create(project=project, event_type=event_type, description=description)


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

            messages.success(request, f'Order from {order.supplier_name} created.')
            return redirect('projects:detail', pk=project_pk)
    else:
        form = MaterialOrderForm()
    return render(request, 'orders/form.html', {'form': form, 'project': project, 'action': 'Create'})


def detail_view(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    return render(request, 'orders/detail.html', {'order': order})


def edit_view(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    old_status = order.status
    if request.method == 'POST':
        form = MaterialOrderForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save()
            order.items.all().delete()
            _save_items(order, request.POST.get('items_data', '[]'))

            desc = f'Order from {order.supplier_name} edited — {order.items.count()} items, TZS {order.total_cost:,.0f}'
            if order.status != old_status:
                desc += f' (status: {dict(MaterialOrder.STATUS_CHOICES).get(old_status)} → {order.get_status_display()})'
            _log(order.project, 'order_edit', desc)

            # Advance project if order just became non-draft
            if old_status == 'draft' and order.status != 'draft' and order.project.status == 'planning':
                order.project.status = 'ordered'
                order.project.save(update_fields=['status'])
                _log(order.project, 'status', 'Status changed: Planning → Materials Ordered')

            messages.success(request, 'Order updated.')
            return redirect('orders:detail', pk=order.pk)
    else:
        form = MaterialOrderForm(instance=order)
    existing_items = list(order.items.values('material_name', 'description', 'quantity', 'unit', 'unit_cost'))
    return render(request, 'orders/form.html', {
        'form': form, 'order': order,
        'project': order.project,
        'existing_items': existing_items,
        'action': 'Edit',
    })


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


@require_POST
def update_status(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in MaterialOrder.STATUS_CHOICES]
    if new_status in valid and new_status != order.status:
        old_label = order.get_status_display()
        order.status = new_status
        if new_status == 'received':
            order.actual_delivery = timezone.now().date()
        order.save()

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
