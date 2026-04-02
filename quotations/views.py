import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string

from .models import Quotation, QuotationItem, QuotationMaterial, Material
from .forms import QuotationForm, QuotationItemForm, QuotationMaterialForm


def _auto_expire():
    """Bulk-expire any draft/sent quotations whose valid_until date has passed."""
    today = timezone.now().date()
    Quotation.objects.filter(
        status__in=['draft', 'sent'],
        valid_until__lt=today,
    ).update(status='expired')

DEFAULT_MATERIALS = [
    ('Aluminium White 8cm',   120000),
    ('Aluminium Grey 8cm',    125000),
    ('Aluminium Bronze 10cm', 150000),
    ('uPVC White 98',          90000),
    ('uPVC Grey 115',          95000),
]


def list_view(request):
    _auto_expire()
    qs = Quotation.objects.all()
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            client_name__icontains=search
        ) | qs.filter(quote_no__icontains=search) | qs.filter(project_name__icontains=search)
    context = {
        'quotations': qs,
        'status_filter': status_filter,
        'search': search,
        'status_choices': Quotation.STATUS_CHOICES,
        'today': timezone.now().date(),
    }
    return render(request, 'quotations/list.html', context)


def create_view(request):
    if request.method == 'POST':
        form = QuotationForm(request.POST)
        if form.is_valid():
            quotation = form.save()

            # Save items from JSON payload
            items_json = request.POST.get('items_data', '[]')
            try:
                items = json.loads(items_json)
                for i, item in enumerate(items):
                    if item.get('item_type') and item.get('width') and item.get('height'):
                        QuotationItem.objects.create(
                            quotation=quotation,
                            item_type=item['item_type'],
                            description=item.get('description', ''),
                            width=Decimal(str(item['width'])),
                            height=Decimal(str(item['height'])),
                            quantity=int(item.get('quantity', 1)),
                            order=i,
                        )
            except (json.JSONDecodeError, KeyError, Exception):
                pass

            # Save materials from JSON payload
            mats_json = request.POST.get('materials_data', '[]')
            try:
                mats = json.loads(mats_json)
                for i, mat in enumerate(mats):
                    if mat.get('material_name') and mat.get('price_per_sqm'):
                        QuotationMaterial.objects.create(
                            quotation=quotation,
                            material_name=mat['material_name'],
                            price_per_sqm=Decimal(str(mat['price_per_sqm'])),
                            notes=mat.get('notes', ''),
                            order=i,
                        )
            except (json.JSONDecodeError, KeyError, Exception):
                pass

            # If no materials were provided, add defaults
            if not quotation.quote_materials.exists():
                for i, (name, price) in enumerate(DEFAULT_MATERIALS):
                    QuotationMaterial.objects.create(
                        quotation=quotation,
                        material_name=name,
                        price_per_sqm=Decimal(str(price)),
                        order=i,
                    )

            messages.success(request, f'Quotation {quotation.quote_no} created successfully.')
            if request.POST.get('_action') == 'save_pdf':
                return redirect(reverse('quotations:pdf', args=[quotation.pk]))
            return redirect('quotations:detail', pk=quotation.pk)
    else:
        form = QuotationForm()

    context = {
        'form': form,
        'default_materials': DEFAULT_MATERIALS,
        'action': 'Create',
    }
    return render(request, 'quotations/form.html', context)


def detail_view(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    # Auto-expire this quote if its valid_until date has passed
    if quotation.status in ('draft', 'sent') and quotation.valid_until and quotation.valid_until < timezone.now().date():
        quotation.status = 'expired'
        quotation.save(update_fields=['status'])
    context = {
        'quotation': quotation,
        'items': quotation.items.all(),
        'material_options': quotation.material_options,
        'accepted_mat_pk': quotation.accepted_material_id,
    }
    return render(request, 'quotations/detail.html', context)


def edit_view(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == 'POST':
        form = QuotationForm(request.POST, instance=quotation)
        if form.is_valid():
            quotation = form.save()

            # Rebuild items
            items_json = request.POST.get('items_data', '[]')
            try:
                items = json.loads(items_json)
                quotation.items.all().delete()
                for i, item in enumerate(items):
                    if item.get('item_type') and item.get('width') and item.get('height'):
                        QuotationItem.objects.create(
                            quotation=quotation,
                            item_type=item['item_type'],
                            description=item.get('description', ''),
                            width=Decimal(str(item['width'])),
                            height=Decimal(str(item['height'])),
                            quantity=int(item.get('quantity', 1)),
                            order=i,
                        )
            except Exception:
                pass

            # Rebuild materials
            mats_json = request.POST.get('materials_data', '[]')
            try:
                mats = json.loads(mats_json)
                quotation.quote_materials.all().delete()
                for i, mat in enumerate(mats):
                    if mat.get('material_name') and mat.get('price_per_sqm'):
                        QuotationMaterial.objects.create(
                            quotation=quotation,
                            material_name=mat['material_name'],
                            price_per_sqm=Decimal(str(mat['price_per_sqm'])),
                            notes=mat.get('notes', ''),
                            order=i,
                        )
            except Exception:
                pass

            messages.success(request, f'Quotation {quotation.quote_no} updated.')
            if request.POST.get('_action') == 'save_pdf':
                return redirect(reverse('quotations:pdf', args=[quotation.pk]))
            return redirect('quotations:detail', pk=quotation.pk)
    else:
        form = QuotationForm(instance=quotation)

    context = {
        'form': form,
        'quotation': quotation,
        'items': list(quotation.items.values('item_type', 'description', 'width', 'height', 'quantity')),
        'materials': list(quotation.quote_materials.values('material_name', 'price_per_sqm', 'notes')),
        'action': 'Edit',
    }
    return render(request, 'quotations/form.html', context)


def delete_view(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == 'POST':
        no = quotation.quote_no
        quotation.delete()
        messages.success(request, f'Quotation {no} deleted.')
        return redirect('quotations:list')
    return render(request, 'quotations/confirm_delete.html', {'quotation': quotation})


def pdf_view(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    options = quotation.material_options

    if quotation.accepted_material_id:
        # FINAL document — only the accepted option
        selected = next(
            (opt for opt in options if opt['material'].pk == quotation.accepted_material_id),
            options[0] if options else None,
        )
        context = {
            'quotation': quotation,
            'items': quotation.items.all(),
            'selected_option': selected,
            'all_options': [],          # hide comparison — final doc
            'accepted_mat_pk': quotation.accepted_material_id,
            'is_final': True,
        }
    else:
        # DRAFT/SENT — show every option in full so the client can choose
        context = {
            'quotation': quotation,
            'items': quotation.items.all(),
            'selected_option': None,    # no single highlight — show all
            'all_options': options,
            'accepted_mat_pk': None,
            'is_final': False,
        }
    return render(request, 'quotations/pdf.html', context)


@require_POST
def accept_option(request, pk):
    """Mark a specific material option as accepted and set status to accepted."""
    quotation = get_object_or_404(Quotation, pk=pk)
    mat_pk = request.POST.get('material_pk')
    material = get_object_or_404(QuotationMaterial, pk=mat_pk, quotation=quotation)
    quotation.accepted_material = material
    quotation.status = 'accepted'
    quotation.save(update_fields=['accepted_material', 'status'])
    messages.success(request, f'Quotation accepted — "{material.material_name}" selected by client.')
    return redirect('quotations:detail', pk=pk)


@require_POST
def update_status(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in Quotation.STATUS_CHOICES]
    if new_status in valid:
        # Clear accepted_material if reverting from accepted
        if new_status != 'accepted' and quotation.accepted_material:
            quotation.accepted_material = None
            quotation.status = new_status
            quotation.save(update_fields=['status', 'accepted_material'])
        else:
            quotation.status = new_status
            quotation.save(update_fields=['status'])
        messages.success(request, f'Status updated to {quotation.get_status_display()}.')
    return redirect('quotations:detail', pk=pk)
