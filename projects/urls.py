from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('projects/', views.project_list, name='project_list'),
    path('projects/create/', views.project_create, name='project_create'),
    path('projects/<int:pk>/', views.project_detail, name='project_detail'),
    path('projects/<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('projects/<int:pk>/delete/', views.project_delete, name='project_delete'),

    # Add items to project
    path('projects/<int:pk>/add-material/', views.add_material, name='add_material'),
    path('projects/<int:pk>/add-labor/', views.add_labor, name='add_labor'),
    path('projects/<int:pk>/add-transport/', views.add_transport, name='add_transport'),
    path('projects/<int:pk>/add-expense/', views.add_expense, name='add_expense'),
    path('projects/<int:pk>/add-payment/', views.add_payment, name='add_payment'),
    path('projects/<int:pk>/add-milestone/', views.add_milestone, name='add_milestone'),
    path('projects/<int:pk>/add-team-member/', views.add_team_member, name='add_team_member'),
    path('projects/<int:pk>/add-task/', views.add_task, name='add_task'),

    # Toggle/update
    path('projects/<int:pk>/milestone/<int:milestone_id>/toggle/', views.toggle_milestone, name='toggle_milestone'),
    path('projects/<int:pk>/task/<int:task_id>/status/', views.update_task_status, name='update_task_status'),
    path('projects/<int:pk>/delete/<str:item_type>/<int:item_id>/', views.delete_item, name='delete_item'),

    # Analytics & Export
    path('analytics/', views.analytics_view, name='analytics'),
    path('export/json/', views.export_projects_json, name='export_json'),
    path('load-demo-data/', views.load_demo_data, name='load_demo_data'),

    # Auth
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
