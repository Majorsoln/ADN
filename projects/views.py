from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum

from .models import Project
from .forms import ProjectForm
from office.models import OfficeIncome


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
                'name': q.project_name or f"Project – {q.client_name}",
                'client_name':  q.client_name,
                'client_phone': q.client_phone,
                'quotation': q,
            }
        except Quotation.DoesNotExist:
            pass

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            messages.success(request, f'Project "{project.name}" created.')
            return redirect('projects:detail', pk=project.pk)
    else:
        form = ProjectForm(initial=initial)
    return render(request, 'projects/form.html', {'form': form, 'action': 'Create'})


def detail_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    orders  = project.orders.all()
    return render(request, 'projects/detail.html', {
        'project': project,
        'orders':  orders,
    })


def edit_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            project = form.save()
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
    """Final project report: revenue, costs, profit."""
    project = get_object_or_404(Project, pk=pk)
    orders  = project.orders.all()
    return render(request, 'projects/report.html', {
        'project': project,
        'orders':  orders,
    })


def complete_view(request, pk):
    """Mark project as completed and record profit to OfficeIncome."""
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        project.status = 'completed'
        project.completion_date = timezone.now().date()
        project.save()
        # Record profit as office income
        profit = project.gross_profit
        if profit > 0:
            OfficeIncome.objects.get_or_create(
                project=project,
                source='project_profit',
                defaults={
                    'amount': profit,
                    'date': project.completion_date,
                    'description': f'Profit from project: {project.name}',
                }
            )
        messages.success(request, f'Project completed. Gross profit TZS {profit:,.0f} recorded.')
        return redirect('projects:report', pk=pk)
    return render(request, 'projects/confirm_complete.html', {'project': project})
