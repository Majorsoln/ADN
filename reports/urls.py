from django.urls import path
from . import views

urlpatterns = [
    path('', views.reports_dashboard, name='reports_dashboard'),
    path('invoice/create/', views.create_invoice, name='create_invoice'),
    path('invoice/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoice/<int:pk>/add-item/', views.add_invoice_item, name='add_invoice_item'),
    path('invoice/<int:pk>/pdf/', views.generate_invoice_pdf, name='invoice_pdf'),
    path('quote/create/', views.create_quote, name='create_quote'),
    path('quote/<int:pk>/pdf/', views.generate_quote_pdf, name='quote_pdf'),
    path('project/<int:pk>/report-pdf/', views.generate_project_report_pdf, name='project_report_pdf'),
    path('financial-summary-pdf/', views.financial_summary_pdf, name='financial_summary_pdf'),
]
