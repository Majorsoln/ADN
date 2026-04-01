from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('quotations/', include('quotations.urls')),
    path('invoices/', include('invoices.urls')),
    path('projects/', include('projects.urls')),
    path('orders/', include('orders.urls')),
    path('office/', include('office.urls')),
    path('finance/', include('finance.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
