from django.contrib import admin
from .models import OfficeServiceRecord, OfficeServicePayment, OfficeServiceRate, OfficeIncome


class OfficeServicePaymentInline(admin.TabularInline):
    model = OfficeServicePayment
    extra = 0
    fields = ['payment_date', 'amount', 'payment_method', 'reference']


@admin.register(OfficeServiceRate)
class OfficeServiceRateAdmin(admin.ModelAdmin):
    list_display = ['rate_per_window', 'rate_per_door', 'effective_from', 'is_active']
    list_editable = ['is_active']


@admin.register(OfficeServiceRecord)
class OfficeServiceRecordAdmin(admin.ModelAdmin):
    list_display  = ['client_name', 'num_windows', 'num_doors', 'total_charge_display', 'total_paid_display', 'balance_display', 'status', 'date_recorded']
    list_filter   = ['status', 'date_recorded']
    search_fields = ['client_name']
    inlines       = [OfficeServicePaymentInline]

    def total_charge_display(self, obj): return f"TZS {obj.total_charge:,.0f}"
    total_charge_display.short_description = 'Total Charge'
    def total_paid_display(self, obj): return f"TZS {obj.total_paid:,.0f}"
    total_paid_display.short_description = 'Paid'
    def balance_display(self, obj): return f"TZS {obj.balance:,.0f}"
    balance_display.short_description = 'Balance'


@admin.register(OfficeIncome)
class OfficeIncomeAdmin(admin.ModelAdmin):
    list_display = ['source', 'amount', 'date', 'description']
    list_filter  = ['source', 'date']
