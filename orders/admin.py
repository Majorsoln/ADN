from django.contrib import admin
from .models import MaterialOrder, MaterialOrderItem


class MaterialOrderItemInline(admin.TabularInline):
    model = MaterialOrderItem
    extra = 1
    fields = ['material_name', 'description', 'quantity', 'unit', 'unit_cost']


@admin.register(MaterialOrder)
class MaterialOrderAdmin(admin.ModelAdmin):
    list_display  = ['project', 'supplier_name', 'order_date', 'expected_delivery', 'status', 'total_cost_display']
    list_filter   = ['status', 'order_date']
    search_fields = ['supplier_name', 'project__name']
    inlines       = [MaterialOrderItemInline]

    def total_cost_display(self, obj):
        return f"TZS {obj.total_cost:,.0f}"
    total_cost_display.short_description = 'Total Cost'
