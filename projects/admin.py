from django.contrib import admin
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display  = ['name', 'client_name', 'status', 'start_date', 'target_date', 'completion_date', 'revenue_display', 'materials_cost_display', 'profit_display']
    list_filter   = ['status', 'start_date']
    search_fields = ['name', 'client_name']
    readonly_fields = ['created_at', 'updated_at']

    def revenue_display(self, obj):
        return f"TZS {obj.revenue:,.0f}"
    revenue_display.short_description = 'Revenue'

    def materials_cost_display(self, obj):
        return f"TZS {obj.materials_cost:,.0f}"
    materials_cost_display.short_description = 'Materials Cost'

    def profit_display(self, obj):
        return f"TZS {obj.gross_profit:,.0f}"
    profit_display.short_description = 'Gross Profit'
