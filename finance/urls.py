from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Daily snapshot (homepage)
    path('', views.snapshot_view, name='snapshot'),

    # ── Focused reports ──────────────────────────────────────────────────────
    path('ar/',       views.ar_report_view,       name='ar_report'),
    path('ap/',       views.ap_report_view,       name='ap_report'),
    path('office/',   views.office_report_view,   name='office_report'),
    path('projects/', views.projects_report_view, name='projects_report'),
    path('full/',     views.full_report_view,     name='full_report'),

    # ── Expenses CRUD ────────────────────────────────────────────────────────
    path('expenses/',                    views.expense_list_view,   name='expense_list'),
    path('expenses/add/',                views.expense_add_view,    name='expense_add'),
    path('expenses/<int:pk>/edit/',      views.expense_edit_view,   name='expense_edit'),
    path('expenses/<int:pk>/delete/',    views.expense_delete_view, name='expense_delete'),

    # ── Categories ───────────────────────────────────────────────────────────
    path('categories/',                  views.category_list_view,   name='category_list'),
    path('categories/<int:pk>/toggle/',  views.category_toggle_view, name='category_toggle'),

    # ── Debts / Liabilities ──────────────────────────────────────────────────
    path('debts/',                     views.debt_list_view,        name='debt_list'),
    path('debts/add/',                 views.debt_add_view,         name='debt_add'),
    path('debts/<int:pk>/',            views.debt_detail_view,      name='debt_detail'),
    path('debts/<int:pk>/edit/',       views.debt_edit_view,        name='debt_edit'),
    path('debts/<int:pk>/delete/',     views.debt_delete_view,      name='debt_delete'),
    path('debts/<int:pk>/pay/',        views.debt_add_payment_view, name='debt_pay'),

    # ── Legacy (keep for old bookmarks, not linked in nav) ───────────────────
    path('report/',                    views.report_view,         name='report'),
    path('report/pdf/',                views.report_pdf_view,     name='report_pdf'),
    path('report/save/',               views.save_report_view,    name='save_report'),
    path('archive/',                   views.archive_view,        name='archive'),
    path('archive/<int:pk>/',          views.archive_detail_view, name='archive_detail'),
    path('archive/<int:pk>/delete/',   views.archive_delete_view, name='archive_delete'),
]
