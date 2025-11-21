# cookie_project/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from cookie_app import views as app_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Public routes (no login required)
    path('', app_views.public_home, name='public_home'),
    # Root now serves public home; unified login will be under /app/login/
    path('about/', TemplateView.as_view(template_name='about.html'), name='about'),
    path('menu/', app_views.public_menu, name='public_menu'),
    path('contact/', TemplateView.as_view(template_name='contact.html'), name='contact'),
    
    # App routes (require login) - all under /app/
    path('app/', include('cookie_app.urls')),
    
    # Authentication routes
    path('logout/', app_views.custom_logout, name='logout'),
    path('accounts/', include('allauth.urls')),  # Google OAuth and other social auth
    
    # Pending approval
    path('pending-approval/', TemplateView.as_view(template_name='pending_approval.html'), name='pending_approval'),
]

# Serve media files in development - THIS SHOULD BE OUTSIDE THE urlpatterns
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)