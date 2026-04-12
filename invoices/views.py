from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Invoice, InvoicePayment
from .forms import InvoiceForm, PaymentForm
from accounts.decorators import login_required, editor_required, admin_required


@login_required
def list_view(request):
    qs = Invoice.objects.order_by('-invoice_date')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(client_name__icontains=search) | \
             qs.filter(invoice_no__icontains=search)
    # auto-mark overdue
    today = timezone.now().date()
    qs.filter(status='sent', due_date__lt=today).update(status='overdue')
    context = {
        'invoices': qs,
        'status_filter': status_filter,
        'search': search,
        'status_choices': Invoice.STATUS_CHOICES,
    }
    return render(request, 'invoices/list.html', context)


@editor_required
def create_view(request):
    # Pre-fill from quotation / project if passed in GET or POST
    quote_pk   = request.GET.get('from_quote') or request.POST.get('from_quote')
    project_pk = request.GET.get('from_project') or request.POST.get('from_project')
    initial = {}
    quote_obj = None

    if quote_pk:
        from quotations.models import Quotation
        try:
            q = Quotation.objects.get(pk=quote_pk)
            quote_obj = q
            initial = {
                'client_name':    q.client_name,
                'client_phone':   q.client_phone,
                'client_email':   q.client_email,
                'client_address': q.client_address,
                'quote_ref':      q.quote_no,
                'quotation':      q,
            }
            # Pre-fill contract_amount from the accepted material option
            if q.accepted_material:
                for opt in q.material_options:
                    if opt['material'].pk == q.accepted_material_id:
                        initial['contract_amount'] = opt['grand']
                        break
            # Discover linked project automatically if not already provided
            if not project_pk:
                try:
                    project_pk = str(q.project.pk)
                except Exception:
                    pass
        except Quotation.DoesNotExist:
            pass

    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save()
            # Auto-link invoice back to the originating project
            if project_pk:
                from projects.models import Project, ProjectEvent
                try:
                    project = Project.objects.get(pk=project_pk)
                    if not project.invoice_id:
                        project.invoice = invoice
                        project.save(update_fields=['invoice'])
                        ProjectEvent.objects.create(
                            project=project,
                            event_type='invoice',
                            description=(
                                f'Invoice {invoice.invoice_no} created and linked '
                                f'(contract TZS {invoice.contract_amount:,.0f}).'
                            ),
                        )
                    messages.success(request,
                        f'Invoice {invoice.invoice_no} created and linked to project.')
                    return redirect('projects:detail', pk=project.pk)
                except Project.DoesNotExist:
                    pass
            messages.success(request, f'Invoice {invoice.invoice_no} created.')
            return redirect('invoices:detail', pk=invoice.pk)
    else:
        form = InvoiceForm(initial=initial)

    return render(request, 'invoices/form.html', {
        'form':       form,
        'action':     'Create',
        'quote_pk':   quote_pk,
        'project_pk': project_pk,
    })


@login_required
def detail_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    payment_form = PaymentForm()
    context = {
        'invoice': invoice,
        'payments': invoice.payments.all(),
        'payment_form': payment_form,
    }
    return render(request, 'invoices/detail.html', context)


@editor_required
def edit_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            invoice = form.save()
            messages.success(request, f'Invoice {invoice.invoice_no} updated.')
            return redirect('invoices:detail', pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
    return render(request, 'invoices/form.html', {'form': form, 'invoice': invoice, 'action': 'Edit'})


@admin_required
def delete_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        no = invoice.invoice_no
        invoice.delete()
        messages.success(request, f'Invoice {no} deleted.')
        return redirect('invoices:list')
    return render(request, 'invoices/confirm_delete.html', {'invoice': invoice})


@login_required
def pdf_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    return render(request, 'invoices/pdf.html', {'invoice': invoice, 'for_pdf': True})


@editor_required
@require_POST
def add_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    form = PaymentForm(request.POST)
    if form.is_valid():
        payment = form.save(commit=False)
        payment.invoice = invoice
        payment.save()
        # Update status if fully paid (include advance + all installments)
        total_paid = invoice.advance_paid + sum(p.amount for p in invoice.payments.all())
        if total_paid >= invoice.contract_amount:
            invoice.status = 'paid'
            invoice.save(update_fields=['status'])
        # Log payment event on every linked project
        from projects.models import ProjectEvent
        ref_suffix = f', Ref: {payment.reference}' if payment.reference else ''
        balance = invoice.contract_amount - total_paid
        balance_note = ''
        if balance < 0:
            balance_note = f' — ⚠ Overpaid by TZS {abs(balance):,.0f}'
        elif balance == 0:
            balance_note = ' — Invoice fully paid ✓'
        else:
            balance_note = f' — Balance remaining TZS {balance:,.0f}'
        for project in invoice.projects.all():
            ProjectEvent.objects.create(
                project=project,
                event_type='invoice',
                description=(
                    f'Client payment received: TZS {payment.amount:,.0f} '
                    f'({payment.get_payment_method_display()}) — '
                    f'Invoice {invoice.invoice_no}{ref_suffix}{balance_note}'
                ),
            )
        if total_paid > invoice.contract_amount:
            overpaid = total_paid - invoice.contract_amount
            messages.warning(request,
                f'Payment recorded. Note: Total paid (TZS {total_paid:,.0f}) exceeds '
                f'contract amount (TZS {invoice.contract_amount:,.0f}) by TZS {overpaid:,.0f}.'
            )
        else:
            messages.success(request, f'Payment of TZS {payment.amount:,.0f} recorded.')
    else:
        messages.error(request, 'Invalid payment data.')
    return redirect('invoices:detail', pk=pk)


@editor_required
@require_POST
def update_status(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in Invoice.STATUS_CHOICES]
    if new_status in valid:
        invoice.status = new_status
        invoice.save(update_fields=['status'])
        messages.success(request, f'Status updated to {invoice.get_status_display()}.')
    return redirect('invoices:detail', pk=pk)
