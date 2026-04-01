from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('project/<int:project_pk>/new/', views.create_view,   name='create'),
    path('<int:pk>/',                     views.detail_view,   name='detail'),
    path('<int:pk>/edit/',                views.edit_view,     name='edit'),
    path('<int:pk>/delete/',              views.delete_view,   name='delete'),
    path('<int:pk>/status/',              views.update_status, name='update_status'),
]
