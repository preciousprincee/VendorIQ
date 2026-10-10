from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from . import admin_pages

urlpatterns = [
    # Custom admin-only pages (Revenue, System Health, Support, Plans &
    # Settings) - listed before the admin.site.urls include below so they
    # resolve directly rather than falling through a failed lookup inside
    # it first. Each is wrapped in admin.site.admin_view, the same
    # mechanism Django's own admin uses, so login/permission/CSRF handling
    # matches every other admin page exactly.
    path('admin/revenue/', admin.site.admin_view(admin_pages.revenue_view), name='admin_revenue'),
    path('admin/system-health/', admin.site.admin_view(admin_pages.system_health_view), name='admin_system_health'),
    path('admin/support/', admin.site.admin_view(admin_pages.support_view), name='admin_support'),
    path('admin/ai-usage/', admin.site.admin_view(admin_pages.ai_usage_view), name='admin_ai_usage'),
    path('admin/ai-usage/<uuid:user_id>/', admin.site.admin_view(admin_pages.ai_user_messages_view), name='admin_ai_user_messages'),
    path('admin/plans/', admin.site.admin_view(admin_pages.settings_view), name='admin_plan_settings'),
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/stores/', include('apps.stores.urls')),
    path('api/stores/', include('apps.products.urls')),
    path('api/stores/', include('apps.sales.urls')),
    path('api/stores/', include('apps.customers.urls')),
    path('api/stores/', include('apps.invoices.urls')),
    path('api/stores/', include('apps.insights.urls')),
    path('api/stores/', include('apps.expenses.urls')),
    path('api/ai/', include('apps.ai.urls')),
    path('api/billing/', include('apps.billing.urls')),
    path('api/referrals/', include('apps.referrals.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/health/', include('vendoriq.health')),
]

# Product photos, etc. In production put a real web server or object storage
# in front of MEDIA_ROOT instead of relying on this.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
