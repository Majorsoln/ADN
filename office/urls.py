from django.urls import path
from . import views

app_name = 'office'

urlpatterns = [
    # Service records
    path('service/',                   views.service_list,        name='service_list'),
    path('service/new/',               views.service_create,      name='service_create'),
    path('service/<int:pk>/',          views.service_detail,      name='service_detail'),
    path('service/<int:pk>/edit/',     views.service_edit,        name='service_edit'),
    path('service/<int:pk>/delete/',   views.service_delete,      name='service_delete'),
    path('service/<int:pk>/pay/',      views.service_add_payment, name='service_pay'),
    # Rates
    path('rates/',                     views.rate_list,           name='rates'),
    # Income
    path('income/',                    views.income_overview,     name='income'),
    path('income/add/',                views.income_add,          name='income_add'),
    path('income/<int:pk>/delete/',    views.income_delete,       name='income_delete'),
]
