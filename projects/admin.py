from django.contrib import admin
from .models import (
    Project, TeamMember, Milestone, Material,
    LaborCost, TransportCost, OtherExpense, Payment,
    ActivityLog, Task
)


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0


class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0


class MaterialInline(admin.TabularInline):
    model = Material
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'client_name', 'status', 'priority', 'budget', 'completion_percentage', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['title', 'client_name', 'location']
    inlines = [TeamMemberInline, MilestoneInline, MaterialInline]


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'role', 'phone']
    list_filter = ['role']


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'quantity', 'unit', 'unit_price']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['project', 'amount', 'method', 'date']
    list_filter = ['method', 'date']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'assigned_to', 'status', 'due_date']
    list_filter = ['status']


admin.site.register(Milestone)
admin.site.register(LaborCost)
admin.site.register(TransportCost)
admin.site.register(OtherExpense)
admin.site.register(ActivityLog)
