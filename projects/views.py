from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q, F, Avg
from django.utils import timezone
from decimal import Decimal
import json

from .models import (
    Project, TeamMember, Milestone, Material,
    LaborCost, TransportCost, OtherExpense, Payment,
    ActivityLog, Task
)
from .forms import (
    ProjectForm, TeamMemberForm, MilestoneForm, MaterialForm,
    LaborCostForm, TransportCostForm, OtherExpenseForm,
    PaymentForm, TaskForm
)
from reports.models import Invoice, Quote, ProjectReport


def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created successfully! Welcome to ADN Project Manager.')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    projects = Project.objects.all()
    total_projects = projects.count()
    active_projects = projects.filter(status='in_progress').count()
    completed_projects = projects.filter(status='completed').count()
    planning_projects = projects.filter(status='planning').count()
    overdue_projects = projects.filter(
        end_date__lt=timezone.now().date()
    ).exclude(status__in=['completed', 'archived']).count()

    total_budget = projects.aggregate(total=Sum('budget'))['total'] or Decimal('0')

    total_revenue = Decimal('0')
    total_expenses = Decimal('0')
    for p in projects:
        total_revenue += p.total_revenue
        total_expenses += p.total_expenses

    total_profit = total_revenue - total_expenses

    recent_activities = ActivityLog.objects.select_related('project', 'user')[:10]
    recent_projects = projects[:6]

    status_data = {
        'planning': planning_projects,
        'in_progress': active_projects,
        'completed': completed_projects,
        'overdue': overdue_projects,
    }

    context = {
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'planning_projects': planning_projects,
        'overdue_projects': overdue_projects,
        'total_budget': total_budget,
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'total_profit': total_profit,
        'recent_activities': recent_activities,
        'recent_projects': recent_projects,
        'status_data': json.dumps(status_data),
    }
    return render(request, 'projects/dashboard.html', context)


@login_required
def project_list(request):
    projects = Project.objects.all()

    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    search = request.GET.get('search', '')

    if status_filter:
        projects = projects.filter(status=status_filter)
    if priority_filter:
        projects = projects.filter(priority=priority_filter)
    if search:
        projects = projects.filter(
            Q(title__icontains=search) |
            Q(client_name__icontains=search) |
            Q(location__icontains=search)
        )

    context = {
        'projects': projects,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'search': search,
    }
    return render(request, 'projects/project_list.html', context)


@login_required
def project_create(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Created project: {project.title}'
            )
            messages.success(request, f'Project "{project.title}" created successfully!')
            return redirect('project_detail', pk=project.pk)
    else:
        form = ProjectForm()
    return render(request, 'projects/project_form.html', {'form': form, 'title': 'Create New Project'})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    materials = project.materials.all()
    labor_costs = project.labor_costs.all()
    transport_costs = project.transport_costs.all()
    other_expenses = project.other_expenses.all()
    payments = project.payments.all()
    milestones = project.milestones.all()
    team_members = project.team_members.all()
    tasks = project.tasks.all()
    activities = project.activities.all()[:20]
    invoices = project.invoices.all()
    quotes = project.quotes.all()
    reports = project.reports.all()

    material_form = MaterialForm()
    labor_form = LaborCostForm()
    transport_form = TransportCostForm()
    expense_form = OtherExpenseForm()
    payment_form = PaymentForm()
    milestone_form = MilestoneForm()
    team_form = TeamMemberForm()
    task_form = TaskForm()
    task_form.fields['assigned_to'].queryset = team_members

    expense_breakdown = {
        'materials': float(project.total_material_cost),
        'labor': float(project.total_labor_cost),
        'transport': float(project.total_transport_cost),
        'other': float(project.total_other_expenses),
    }

    context = {
        'project': project,
        'materials': materials,
        'labor_costs': labor_costs,
        'transport_costs': transport_costs,
        'other_expenses': other_expenses,
        'payments': payments,
        'milestones': milestones,
        'team_members': team_members,
        'tasks': tasks,
        'activities': activities,
        'invoices': invoices,
        'quotes': quotes,
        'reports': reports,
        'material_form': material_form,
        'labor_form': labor_form,
        'transport_form': transport_form,
        'expense_form': expense_form,
        'payment_form': payment_form,
        'milestone_form': milestone_form,
        'team_form': team_form,
        'task_form': task_form,
        'expense_breakdown': json.dumps(expense_breakdown),
    }
    return render(request, 'projects/project_detail.html', context)


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Updated project: {project.title}'
            )
            messages.success(request, 'Project updated successfully!')
            return redirect('project_detail', pk=project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'projects/project_form.html', {'form': form, 'title': f'Edit: {project.title}', 'project': project})


@login_required
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        title = project.title
        project.delete()
        messages.success(request, f'Project "{title}" deleted.')
        return redirect('project_list')
    return render(request, 'projects/project_confirm_delete.html', {'project': project})


@login_required
def add_material(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = MaterialForm(request.POST)
        if form.is_valid():
            material = form.save(commit=False)
            material.project = project
            material.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Added material: {material.name}'
            )
            messages.success(request, f'Material "{material.name}" added.')
    return redirect('project_detail', pk=pk)


@login_required
def add_labor(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = LaborCostForm(request.POST)
        if form.is_valid():
            labor = form.save(commit=False)
            labor.project = project
            labor.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Added labor cost: {labor.description}'
            )
            messages.success(request, 'Labor cost added.')
    return redirect('project_detail', pk=pk)


@login_required
def add_transport(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = TransportCostForm(request.POST)
        if form.is_valid():
            transport = form.save(commit=False)
            transport.project = project
            transport.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Added transport: {transport.from_location} → {transport.to_location}'
            )
            messages.success(request, 'Transport cost added.')
    return redirect('project_detail', pk=pk)


@login_required
def add_expense(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = OtherExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.project = project
            expense.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Added expense: {expense.description}'
            )
            messages.success(request, 'Expense added.')
    return redirect('project_detail', pk=pk)


@login_required
def add_payment(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.project = project
            payment.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Recorded payment: TZS {payment.amount:,.2f}'
            )
            messages.success(request, f'Payment of TZS {payment.amount:,.2f} recorded.')
    return redirect('project_detail', pk=pk)


@login_required
def add_milestone(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = MilestoneForm(request.POST)
        if form.is_valid():
            milestone = form.save(commit=False)
            milestone.project = project
            milestone.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Added milestone: {milestone.title}'
            )
            messages.success(request, f'Milestone "{milestone.title}" added.')
    return redirect('project_detail', pk=pk)


@login_required
def toggle_milestone(request, pk, milestone_id):
    milestone = get_object_or_404(Milestone, pk=milestone_id, project_id=pk)
    milestone.completed = not milestone.completed
    if milestone.completed:
        milestone.completed_date = timezone.now().date()
    else:
        milestone.completed_date = None
    milestone.save()

    completed = milestone.project.milestones.filter(completed=True).count()
    total = milestone.project.milestones.count()
    if total > 0:
        milestone.project.completion_percentage = int((completed / total) * 100)
        milestone.project.save()

    return redirect('project_detail', pk=pk)


@login_required
def add_team_member(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = TeamMemberForm(request.POST)
        if form.is_valid():
            member = form.save(commit=False)
            member.project = project
            member.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Added team member: {member.name} ({member.get_role_display()})'
            )
            messages.success(request, f'{member.name} added to team.')
    return redirect('project_detail', pk=pk)


@login_required
def add_task(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = TaskForm(request.POST)
        form.fields['assigned_to'].queryset = project.team_members.all()
        if form.is_valid():
            task = form.save(commit=False)
            task.project = project
            task.save()
            ActivityLog.objects.create(
                project=project, user=request.user,
                action=f'Created task: {task.title}'
            )
            messages.success(request, f'Task "{task.title}" created.')
    return redirect('project_detail', pk=pk)


@login_required
def update_task_status(request, pk, task_id):
    task = get_object_or_404(Task, pk=task_id, project_id=pk)
    new_status = request.POST.get('status')
    if new_status in dict(Task.STATUS_CHOICES):
        task.status = new_status
        task.save()
    return redirect('project_detail', pk=pk)


@login_required
def delete_item(request, pk, item_type, item_id):
    project = get_object_or_404(Project, pk=pk)
    model_map = {
        'material': Material,
        'labor': LaborCost,
        'transport': TransportCost,
        'expense': OtherExpense,
        'payment': Payment,
        'milestone': Milestone,
        'team': TeamMember,
        'task': Task,
    }
    model = model_map.get(item_type)
    if model:
        item = get_object_or_404(model, pk=item_id, project=project)
        item.delete()
        ActivityLog.objects.create(
            project=project, user=request.user,
            action=f'Deleted {item_type}: {item}'
        )
        messages.success(request, f'{item_type.title()} deleted.')
    return redirect('project_detail', pk=pk)


@login_required
def analytics_view(request):
    projects = Project.objects.all()

    project_budgets = []
    project_expenses = []
    project_revenues = []
    project_labels = []
    for p in projects[:10]:
        project_labels.append(p.title[:20])
        project_budgets.append(float(p.budget))
        project_expenses.append(float(p.total_expenses))
        project_revenues.append(float(p.total_revenue))

    status_counts = {}
    for status, label in Project.STATUS_CHOICES:
        count = projects.filter(status=status).count()
        if count > 0:
            status_counts[label] = count

    monthly_expenses = {}
    for p in projects:
        for m in p.materials.all():
            month_key = m.date_added.strftime('%Y-%m')
            monthly_expenses[month_key] = monthly_expenses.get(month_key, 0) + float(m.total_cost)
        for l in p.labor_costs.all():
            month_key = l.date.strftime('%Y-%m')
            monthly_expenses[month_key] = monthly_expenses.get(month_key, 0) + float(l.amount)

    sorted_months = sorted(monthly_expenses.keys())
    monthly_data = {
        'labels': sorted_months,
        'values': [monthly_expenses[m] for m in sorted_months]
    }

    total_revenue = sum(float(p.total_revenue) for p in projects)
    total_expenses = sum(float(p.total_expenses) for p in projects)
    total_budget = float(projects.aggregate(total=Sum('budget'))['total'] or 0)
    avg_completion = projects.aggregate(avg=Avg('completion_percentage'))['avg'] or 0

    context = {
        'project_labels': json.dumps(project_labels),
        'project_budgets': json.dumps(project_budgets),
        'project_expenses': json.dumps(project_expenses),
        'project_revenues': json.dumps(project_revenues),
        'status_counts': json.dumps(status_counts),
        'monthly_data': json.dumps(monthly_data),
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'total_budget': total_budget,
        'avg_completion': avg_completion,
        'total_profit': total_revenue - total_expenses,
        'project_count': projects.count(),
    }
    return render(request, 'projects/analytics.html', context)


@login_required
def export_projects_json(request):
    projects = Project.objects.all()
    data = []
    for p in projects:
        data.append({
            'title': p.title,
            'client': p.client_name,
            'status': p.status,
            'budget': str(p.budget),
            'total_expenses': str(p.total_expenses),
            'total_revenue': str(p.total_revenue),
            'profit_loss': str(p.profit_loss),
            'completion': p.completion_percentage,
            'start_date': str(p.start_date),
            'end_date': str(p.end_date) if p.end_date else None,
        })

    response = HttpResponse(
        json.dumps(data, indent=2),
        content_type='application/json'
    )
    response['Content-Disposition'] = 'attachment; filename="adn_projects_export.json"'
    return response


@login_required
def load_demo_data(request):
    if request.method == 'POST':
        if Project.objects.exists():
            messages.warning(request, 'Demo data already loaded or projects exist.')
            return redirect('dashboard')

        user = request.user

        p1 = Project.objects.create(
            title='Kigamboni Luxury Villa - Windows & Doors',
            description='Full uPVC window and door installation for a luxury villa in Kigamboni. 24 windows, 8 doors including sliding and casement types.',
            client_name='Hassan Mwinyi',
            client_phone='+255 712 345 678',
            location='Kigamboni, Dar es Salaam',
            status='in_progress',
            priority='high',
            budget=Decimal('45000000'),
            start_date=timezone.now().date() - timezone.timedelta(days=30),
            end_date=timezone.now().date() + timezone.timedelta(days=60),
            completion_percentage=45,
            created_by=user,
        )

        Material.objects.bulk_create([
            Material(project=p1, name='uPVC Window Frames (1200x1500mm)', quantity=24, unit='pcs', unit_price=Decimal('350000')),
            Material(project=p1, name='Tempered Glass 6mm', quantity=48, unit='sqm', unit_price=Decimal('85000')),
            Material(project=p1, name='uPVC Door Frames', quantity=8, unit='pcs', unit_price=Decimal('650000')),
            Material(project=p1, name='Door Hardware Sets', quantity=8, unit='sets', unit_price=Decimal('120000')),
            Material(project=p1, name='Silicon Sealant', quantity=30, unit='tubes', unit_price=Decimal('15000')),
            Material(project=p1, name='Mounting Brackets', quantity=100, unit='pcs', unit_price=Decimal('5000')),
        ])

        LaborCost.objects.bulk_create([
            LaborCost(project=p1, description='Window Installation Team', worker_name='Team A', days=15, daily_rate=Decimal('80000'), amount=Decimal('1200000')),
            LaborCost(project=p1, description='Door Installation', worker_name='Team B', days=10, daily_rate=Decimal('80000'), amount=Decimal('800000')),
        ])

        TransportCost.objects.create(project=p1, vehicle_type='Truck', from_location='Kariakoo Warehouse', to_location='Kigamboni Site', cost=Decimal('350000'))
        OtherExpense.objects.create(project=p1, category='permits', description='Building permit fees', amount=Decimal('250000'))
        Payment.objects.bulk_create([
            Payment(project=p1, amount=Decimal('20000000'), method='bank_transfer', reference='NMB-2024-001'),
            Payment(project=p1, amount=Decimal('10000000'), method='mobile_money', reference='M-Pesa TXN-445566'),
        ])

        Milestone.objects.bulk_create([
            Milestone(project=p1, title='Site Survey & Measurements', completed=True, order=1, completed_date=timezone.now().date() - timezone.timedelta(days=25)),
            Milestone(project=p1, title='Material Procurement', completed=True, order=2, completed_date=timezone.now().date() - timezone.timedelta(days=15)),
            Milestone(project=p1, title='Window Installation', completed=False, order=3, due_date=timezone.now().date() + timezone.timedelta(days=15)),
            Milestone(project=p1, title='Door Installation', completed=False, order=4, due_date=timezone.now().date() + timezone.timedelta(days=35)),
            Milestone(project=p1, title='Final Inspection', completed=False, order=5, due_date=timezone.now().date() + timezone.timedelta(days=55)),
        ])

        t1 = TeamMember.objects.create(project=p1, name='John Magufuli', role='manager', phone='+255 755 111 222', daily_rate=Decimal('100000'))
        t2 = TeamMember.objects.create(project=p1, name='Amina Said', role='engineer', phone='+255 755 333 444', daily_rate=Decimal('80000'))
        TeamMember.objects.create(project=p1, name='Rashid Omary', role='installer', phone='+255 755 555 666', daily_rate=Decimal('50000'))

        Task.objects.bulk_create([
            Task(project=p1, title='Complete ground floor windows', assigned_to=t2, status='in_progress', due_date=timezone.now().date() + timezone.timedelta(days=10)),
            Task(project=p1, title='Order additional sealant', assigned_to=t1, status='todo'),
            Task(project=p1, title='First floor measurements', assigned_to=t2, status='done'),
        ])

        p2 = Project.objects.create(
            title='Masaki Office Complex - Aluminum Facade',
            description='Complete aluminum curtain wall and facade system for 5-story office building.',
            client_name='Victoria Investments Ltd',
            client_phone='+255 222 667 788',
            location='Masaki, Dar es Salaam',
            status='planning',
            priority='high',
            budget=Decimal('120000000'),
            start_date=timezone.now().date() + timezone.timedelta(days=15),
            end_date=timezone.now().date() + timezone.timedelta(days=180),
            completion_percentage=0,
            created_by=user,
        )

        Milestone.objects.bulk_create([
            Milestone(project=p2, title='Architectural Review', completed=False, order=1, due_date=timezone.now().date() + timezone.timedelta(days=20)),
            Milestone(project=p2, title='Material Sourcing', completed=False, order=2),
            Milestone(project=p2, title='Fabrication', completed=False, order=3),
            Milestone(project=p2, title='Installation Phase 1', completed=False, order=4),
            Milestone(project=p2, title='Installation Phase 2', completed=False, order=5),
        ])

        p3 = Project.objects.create(
            title='Mikocheni Residential - Sliding Doors',
            description='6 large sliding door units with mosquito mesh for residential property.',
            client_name='Grace Mushi',
            client_phone='+255 784 556 677',
            location='Mikocheni B, Dar es Salaam',
            status='completed',
            priority='medium',
            budget=Decimal('8500000'),
            start_date=timezone.now().date() - timezone.timedelta(days=45),
            end_date=timezone.now().date() - timezone.timedelta(days=5),
            completion_percentage=100,
            created_by=user,
        )

        Material.objects.bulk_create([
            Material(project=p3, name='Aluminum Sliding Door Frame (2400x2100mm)', quantity=6, unit='pcs', unit_price=Decimal('750000')),
            Material(project=p3, name='Tinted Glass 8mm', quantity=12, unit='sqm', unit_price=Decimal('95000')),
            Material(project=p3, name='Mosquito Mesh Screens', quantity=6, unit='pcs', unit_price=Decimal('85000')),
        ])

        LaborCost.objects.create(project=p3, description='Installation Team', worker_name='Team C', days=8, daily_rate=Decimal('70000'), amount=Decimal('560000'))
        TransportCost.objects.create(project=p3, vehicle_type='Pickup', from_location='Workshop', to_location='Mikocheni B', cost=Decimal('150000'))

        Payment.objects.bulk_create([
            Payment(project=p3, amount=Decimal('4000000'), method='cash', reference='CASH-001'),
            Payment(project=p3, amount=Decimal('4500000'), method='bank_transfer', reference='CRDB-2024-055'),
        ])

        Milestone.objects.bulk_create([
            Milestone(project=p3, title='Measurements', completed=True, order=1, completed_date=timezone.now().date() - timezone.timedelta(days=40)),
            Milestone(project=p3, title='Fabrication', completed=True, order=2, completed_date=timezone.now().date() - timezone.timedelta(days=25)),
            Milestone(project=p3, title='Installation', completed=True, order=3, completed_date=timezone.now().date() - timezone.timedelta(days=10)),
            Milestone(project=p3, title='Client Handover', completed=True, order=4, completed_date=timezone.now().date() - timezone.timedelta(days=5)),
        ])

        p4 = Project.objects.create(
            title='Mbezi Beach Hotel - Louvered Windows',
            description='Custom louvered windows for beach hotel renovation. 40 units various sizes.',
            client_name='Mbezi Beach Resort',
            client_phone='+255 222 889 900',
            location='Mbezi Beach, Dar es Salaam',
            status='review',
            priority='medium',
            budget=Decimal('28000000'),
            start_date=timezone.now().date() - timezone.timedelta(days=60),
            end_date=timezone.now().date() + timezone.timedelta(days=10),
            completion_percentage=85,
            created_by=user,
        )

        Material.objects.bulk_create([
            Material(project=p4, name='Aluminum Louvre Frames', quantity=40, unit='pcs', unit_price=Decimal('280000')),
            Material(project=p4, name='Glass Louvre Blades', quantity=320, unit='pcs', unit_price=Decimal('25000')),
            Material(project=p4, name='Operators & Handles', quantity=40, unit='sets', unit_price=Decimal('45000')),
        ])

        LaborCost.objects.create(project=p4, description='Installation Crew', worker_name='Team D', days=20, daily_rate=Decimal('75000'), amount=Decimal('1500000'))
        Payment.objects.create(project=p4, amount=Decimal('15000000'), method='bank_transfer', reference='NMB-2024-089')

        for p in [p1, p2, p3, p4]:
            ActivityLog.objects.create(project=p, user=user, action=f'Project "{p.title}" created with demo data')

        messages.success(request, 'Demo data loaded successfully! 4 sample projects created.')
        return redirect('dashboard')

    return redirect('dashboard')
