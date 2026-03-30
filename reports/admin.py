from django.contrib import admin
from .models import Invoice, InvoiceItem, Quote, QuoteItem, ProjectReport


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


class QuoteItemInline(admin.TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'project', 'client_name', 'total_amount', 'status', 'issue_date']
    list_filter = ['status']
    inlines = [InvoiceItemInline]


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ['quote_number', 'client_name', 'project_name', 'total_amount', 'status']
    list_filter = ['status']
    inlines = [QuoteItemInline]


@admin.register(ProjectReport)
class ProjectReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'prepared_by', 'report_date']


admin.site.register(InvoiceItem)
admin.site.register(QuoteItem)
