from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('',              views.list_view,   name='list'),
    path('new/',          views.create_view, name='create'),
    path('<int:pk>/',     views.detail_view, name='detail'),
    path('<int:pk>/edit/', views.edit_view,  name='edit'),
    path('<int:pk>/delete/', views.delete_view, name='delete'),
    path('<int:pk>/pdf/', views.pdf_view,    name='pdf'),
    path('<int:pk>/pay/', views.add_payment, name='add_payment'),
    path('<int:pk>/status/', views.update_status, name='update_status'),
]
