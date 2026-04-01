from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Project, ProjectEvent
from .forms import ProjectForm
from office.models import OfficeIncome


# ── helpers ──────────────────────────────────────────────────────────────────

def _log(project, event_type, description):
    ProjectEvent.objects.create(project=project, event_type=event_type, description=description)


# ── Views ─────────────────────────────────────────────────────────────────────

def list_view(request):
    qs = Project.objects.all()
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(name__icontains=search) | qs.filter(client_name__icontains=search)
    return render(request, 'projects/list.html', {
        'projects': qs,
        'status_filter': status_filter,
        'search': search,
        'status_choices': Project.STATUS_CHOICES,
    })


def create_view(request):
    # Pre-fill from quotation
    quote_pk = request.GET.get('from_quote')
    initial = {}
    if quote_pk:
        from quotations.models import Quotation
        try:
            q = Quotation.objects.get(pk=quote_pk)
            initial = {
                'name':         q.project_name or f"Project – {q.client_name}",
                'client_name':  q.client_name,
                'client_phone': q.client_phone,
                'quotation':    q,
            }
        except Quotation.DoesNotExist:
            pass

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            _log(project, 'created',
                 f'Project "{project.name}" created for client {project.client_name}.')
            if project.quotation:
                _log(project, 'invoice',
                     f'Quotation {project.quotation.quote_no} linked at creation.')
            messages.success(request, f'Project "{project.name}" created.')
            return redirect('projects:detail', pk=project.pk)
    else:
        form = ProjectForm(initial=initial)
    return render(request, 'projects/form.html', {'form': form, 'action': 'Create'})


def detail_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    orders  = project.orders.prefetch_related('items').all()
    events  = project.events.all()[:40]
    return render(request, 'projects/detail.html', {
        'project': project,
        'orders':  orders,
        'events':  events,
    })


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
    return render(request, 'projects/form.html', {'form': form, 'project': project, 'action': 'Edit'})


def delete_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'Project "{name}" deleted.')
        return redirect('projects:list')
    return render(request, 'projects/confirm_delete.html', {'project': project})


def report_view(request, pk):
    """Final project report — printable as PDF."""
    project = get_object_or_404(Project, pk=pk)
    orders  = project.orders.prefetch_related('items').all()
    events  = project.events.all()
    return render(request, 'projects/report.html', {
        'project': project,
        'orders':  orders,
        'events':  events,
        'today':   timezone.now().date(),
    })


def complete_view(request, pk):
    """Mark project completed and record gross profit to OfficeIncome."""
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        project.status = 'completed'
        project.completion_date = timezone.now().date()
        project.save()
        profit = project.gross_profit
        if profit > 0:
            OfficeIncome.objects.get_or_create(
                project=project,
                source='project_profit',
                defaults={
                    'amount':      profit,
                    'date':        project.completion_date,
                    'description': f'Profit from project: {project.name}',
                }
            )
        _log(project, 'completed',
             f'Project marked completed. Gross profit TZS {profit:,.0f} recorded to office income.')
        messages.success(request, f'Project completed. Gross profit TZS {profit:,.0f} recorded.')
        return redirect('projects:report', pk=pk)
    return render(request, 'projects/confirm_complete.html', {'project': project})


@require_POST
def add_note_view(request, pk):
    """Add a manual note to the project timeline."""
    project = get_object_or_404(Project, pk=pk)
    note = request.POST.get('note', '').strip()
    if note:
        _log(project, 'note', note)
        messages.success(request, 'Note added to project timeline.')
    return redirect('projects:detail', pk=pk)


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
        messages.success(request, f'Status updated to {project.get_status_display()}.')
    return redirect('projects:detail', pk=pk)
