from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    path('',                   views.list_view,     name='list'),
    path('new/',               views.create_view,   name='create'),
    path('<int:pk>/',          views.detail_view,   name='detail'),
    path('<int:pk>/edit/',     views.edit_view,     name='edit'),
    path('<int:pk>/delete/',   views.delete_view,   name='delete'),
    path('<int:pk>/report/',   views.report_view,   name='report'),
    path('<int:pk>/complete/', views.complete_view, name='complete'),
]
