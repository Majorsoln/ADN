from django.contrib import admin
from .models import Invoice, InvoicePayment


class InvoicePaymentInline(admin.TabularInline):
    model = InvoicePayment
    extra = 0
    fields = ['payment_date', 'amount', 'payment_method', 'reference', 'notes']
    readonly_fields = ['created_at']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ['invoice_no', 'client_name', 'invoice_date', 'due_date', 'contract_amount', 'advance_paid', 'balance_due_display', 'status']
    list_filter   = ['status', 'invoice_date']
    search_fields = ['invoice_no', 'client_name', 'quote_ref']
    readonly_fields = ['invoice_no', 'created_at', 'updated_at']
    inlines = [InvoicePaymentInline]
    fieldsets = [
        ('Reference', {'fields': ['invoice_no', 'quote_ref', 'quotation', 'status']}),
        ('Client', {'fields': ['client_name', 'client_phone', 'client_email', 'client_address']}),
        ('Dates', {'fields': ['invoice_date', 'due_date', 'completion_date']}),
        ('Work', {'fields': ['description']}),
        ('Financials', {'fields': ['contract_amount', 'advance_paid']}),
        ('Notes', {'fields': ['notes']}),
        ('Timestamps', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def balance_due_display(self, obj):
        return f"TZS {obj.balance_due:,.0f}"
    balance_due_display.short_description = 'Balance Due'


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'payment_date', 'amount', 'payment_method', 'reference']
    list_filter  = ['payment_method', 'payment_date']
    search_fields = ['invoice__invoice_no', 'reference']
