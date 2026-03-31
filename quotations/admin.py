from django.contrib import admin
from .models import Quotation, QuotationItem, QuotationMaterial, Material


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 1
    fields = ['item_type', 'description', 'width', 'height', 'quantity']


class QuotationMaterialInline(admin.TabularInline):
    model = QuotationMaterial
    extra = 1
    fields = ['material_name', 'price_per_sqm', 'notes', 'order']


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display  = ['quote_no', 'client_name', 'project_name', 'quote_date', 'valid_until', 'status', 'total_area']
    list_filter   = ['status', 'quote_date']
    search_fields = ['quote_no', 'client_name', 'project_name']
    readonly_fields = ['quote_no', 'created_at', 'updated_at']
    inlines = [QuotationItemInline, QuotationMaterialInline]
    fieldsets = [
        ('Reference', {'fields': ['quote_no', 'status']}),
        ('Client', {'fields': ['client_name', 'client_phone', 'client_email', 'client_address']}),
        ('Project', {'fields': ['project_name', 'installation_days', 'quote_date', 'valid_until', 'notes']}),
        ('Discount', {'fields': ['discount_name', 'discount_duration', 'discount_type', 'discount_value']}),
        ('Taxes', {'fields': [
            'vat_enabled', 'vat_rate',
            'service_levy_enabled', 'service_levy_rate',
            'skills_levy_enabled', 'skills_levy_rate',
            'withholding_enabled', 'withholding_rate',
            'custom1_name', 'custom1_rate', 'custom1_enabled',
            'custom2_name', 'custom2_rate', 'custom2_enabled',
        ], 'classes': ['collapse']}),
        ('Timestamps', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def total_area(self, obj):
        return f"{obj.total_area:.2f} m²"
    total_area.short_description = 'Total Area'


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['name', 'price_per_sqm', 'is_active']
    list_editable = ['price_per_sqm', 'is_active']
