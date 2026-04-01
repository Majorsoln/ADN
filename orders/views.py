import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from projects.models import Project
from .models import MaterialOrder, MaterialOrderItem
from .forms import MaterialOrderForm


def create_view(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if request.method == 'POST':
        form = MaterialOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.project = project
            order.save()
            # Save items from JSON
            items_json = request.POST.get('items_data', '[]')
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
            # Update project status
            if project.status == 'planning':
                project.status = 'ordered'
                project.save(update_fields=['status'])
            messages.success(request, f'Material order from {order.supplier_name} created.')
            return redirect('projects:detail', pk=project_pk)
    else:
        form = MaterialOrderForm()
    return render(request, 'orders/form.html', {'form': form, 'project': project, 'action': 'Create'})


def detail_view(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    return render(request, 'orders/detail.html', {'order': order})


def edit_view(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    if request.method == 'POST':
        form = MaterialOrderForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save()
            # Rebuild items
            items_json = request.POST.get('items_data', '[]')
            try:
                items = json.loads(items_json)
                order.items.all().delete()
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
        order.delete()
        messages.success(request, 'Order deleted.')
        return redirect('projects:detail', pk=project_pk)
    return render(request, 'orders/confirm_delete.html', {'order': order})


@require_POST
def update_status(request, pk):
    order = get_object_or_404(MaterialOrder, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in MaterialOrder.STATUS_CHOICES]
    if new_status in valid:
        order.status = new_status
        order.save(update_fields=['status'])
        messages.success(request, f'Order status updated to {order.get_status_display()}.')
    return redirect('orders:detail', pk=pk)
