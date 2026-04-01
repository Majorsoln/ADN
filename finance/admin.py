from django.contrib import admin
from .models import ExpenseCategory, Expense, ReportSnapshot


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'color', 'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    ordering = ('sort_order', 'name')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'category', 'description', 'amount', 'payment_method', 'project')
    list_filter = ('category', 'payment_method', 'date')
    search_fields = ('description', 'paid_to', 'reference')
    date_hierarchy = 'date'
    raw_id_fields = ('project',)


@admin.register(ReportSnapshot)
class ReportSnapshotAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_type', 'period_from', 'period_to', 'generated_at')
    list_filter = ('report_type',)
    readonly_fields = ('generated_at', 'figures')
