# cookie_app/urls.py
from django.urls import path, include
from . import views

urlpatterns = [
    # Authentication
    path('', views.home, name='home'),
    path('login/', views.unified_login, name='home'),
    path('public/', views.public_home, name='public_home'),
    path('login-complete/', views.login_complete, name='login_complete'),
    path('logout/', views.custom_logout, name='logout'),
    path('pending-approval/', views.pending_approval, name='pending_approval'),
    path('customer/register/', views.customer_register, name='customer_register'),
    
    # Email Verification
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('resend-verification/', views.resend_verification_email, name='resend_verification'),
    
    # Dashboard Routes
    path('dashboard/', views.dashboard, name='dashboard'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('customer/dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/profile/', views.staff_profile, name='staff_profile'),

    # Include all your other existing URLs...
    # Kiosk Order System
    path('kiosk/order/', views.kiosk_order, name='kiosk_order'),
    path('kiosk/payment/<int:order_id>/', views.kiosk_payment, name='kiosk_payment'),
    path('kiosk/receipt/<int:order_id>/', views.kiosk_receipt, name='kiosk_receipt'),
    
    # Staff Order System
    path('staff/order-receipt/<int:order_id>/', views.staff_order_receipt, name='staff_order_receipt'),
    
    # Order Management
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/update-status/', views.update_order_status, name='update_order_status'),
    path('orders/<int:order_id>/complete-payment/', views.complete_order_payment, name='complete_order_payment'),
    path('orders/<int:order_id>/verify-gcash/', views.verify_gcash, name='verify_gcash'),
    path('orders/<int:order_id>/confirm-cash/', views.confirm_cash_staff, name='confirm_cash_staff'),
    path('orders/<int:order_id>/void/', views.void_order, name='void_order'),
    path('orders/create/', views.order_create, name='order_create'),

    # Reporting
    path('reports/sales/', views.sales_report, name='sales_report'),
    # Order Management Hub
    path('order-management/', views.order_management, name='order_management'),
    path('staff/notifications/', views.staff_notifications, name='staff_notifications'),
    
    # Inventory Management
    path('inventory/', views.inventory, name='inventory'),
    path('inventory/add/', views.add_cookie, name='add_cookie'),
    path('inventory/<int:pk>/update/', views.update_cookie, name='update_cookie'),
    path('inventory/<int:pk>/delete/', views.delete_cookie, name='delete_cookie'),
    
    # Customer URLs
    path('customer/place-order/', views.place_order, name='place_order'),
    path('customer/cart/', views.customer_cart, name='customer_cart'),
    path('customer/cart/state/', views.cart_state, name='cart_state'),
    path('customer/cart/update/', views.update_cart_item, name='update_cart_item'),
    path('customer/order-status/', views.order_status, name='order_status'),
    path('customer/orders/history/', views.order_history, name='order_history'),
    path('customer/orders/<int:order_id>/cancel/', views.customer_cancel_order, name='customer_cancel_order'),
    path('customer/profile/', views.customer_profile, name='customer_profile'),
    path('customer/delete-account/', views.delete_customer_account, name='delete_customer_account'),
    path('customer/reauth/google/', views.customer_google_reauth, name='customer_google_reauth'),
    path('customer/reauth/complete/', views.customer_reauth_complete, name='customer_reauth_complete'),
    path('customer/loyalty/', views.loyalty_rewards, name='loyalty_rewards'),
    path('customer/notifications/', views.customer_notifications, name='customer_notifications'),
    path('customer/help/', views.customer_help, name='customer_help'),
    path('customer/order-confirmation/<int:order_id>/', views.order_confirmation, name='order_confirmation'),
    # Admin Customer Management
    path('admin/customers/', views.admin_customer_list, name='admin_customer_list'),
    path('admin/customers/<int:customer_id>/orders/', views.admin_customer_orders, name='admin_customer_orders'),
    path('admin/customers/<int:customer_id>/activate/', views.admin_activate_customer, name='admin_activate_customer'),
    path('admin/customers/<int:customer_id>/deactivate/', views.admin_deactivate_customer, name='admin_deactivate_customer'),

    # Admin GCash Verification
    path('admin/gcash-verifications/', views.admin_gcash_verifications, name='admin_gcash_verifications'),

    # Admin Store Settings
    path('admin/settings/', views.admin_store_settings, name='admin_store_settings'),

    # Admin Order Detail
    path('admin/orders/<int:order_id>/', views.admin_order_detail, name='admin_order_detail'),

    # Activity Logs
    path('activity-logs/', views.activity_logs, name='activity_logs'),
    
    # Void Logs
    path('void-logs/', views.void_logs, name='void_logs'),
    path('sales/<int:order_id>/void/', views.void_order, name='void_sale'),
    path('void-modal/', views.void_modal, name='void_modal'),

    # Staff management routes
    path('staff-management/', views.staff_management, name='staff_management'),
    path('staff/approve/<int:staff_id>/', views.approve_staff, name='approve_staff'),
    path('staff/reject/<int:staff_id>/', views.reject_staff, name='reject_staff'),
    path('staff/record-sale/', views.staff_record_sale, name='staff_record_sale'),
    path('record-sale/', views.staff_record_sale, name='record_sale'),
    path('staff/edit/<int:staff_id>/', views.edit_staff, name='edit_staff'),
    path('staff/deactivate/<int:staff_id>/', views.deactivate_staff, name='deactivate_staff'),
    path('staff/activate/<int:staff_id>/', views.activate_staff, name='activate_staff'),
    path('staff/delete/<int:staff_id>/', views.delete_staff, name='delete_staff'),

     # Payment / order processing
    path('customer/process-cash-payment/<int:order_id>/', views.process_cash_payment, name='process_cash_payment'),
    path('customer/process-cash-payment/', views.process_cash_payment, name='process_cash_payment_noid'),
    path('customer/process-gcash-payment/<int:order_id>/', views.process_gcash_payment, name='process_gcash_payment'),
    path('customer/process-card-payment/<int:order_id>/', views.process_card_payment, name='process_card_payment'),
    path('customer/process-maya-payment/<int:order_id>/', views.process_maya_payment, name='process_maya_payment'),
    path('customer/payment/confirm/<int:order_id>/', views.payment_confirm, name='payment_confirm'),
    path('customer/payment/redirect/<str:provider>/<int:order_id>/', views.payment_redirect, name='payment_redirect'),

    # Category management routes
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.add_category, name='add_category'),
    path('categories/<int:pk>/update/', views.update_category, name='update_category'),
    path('categories/<int:pk>/delete/', views.delete_category, name='delete_category'),
    
    # Daily Sales Reporting
    path('daily-sales/', views.daily_sales_report, name='daily_sales_report'),
    path('staff-sales-history/', views.staff_sales_history, name='staff_sales_history'),
    path('admin-sales-monitoring/', views.admin_sales_monitoring, name='admin_sales_monitoring'),
    path('admin-sales-monitoring/csv/', views.admin_sales_monitoring_csv, name='admin_sales_monitoring_csv'),

    # API routes
    path('api/search-cookies/', views.search_cookies, name='search_cookies'),
    path('api/search-customers/', views.search_customers, name='search_customers'),
    path('api/search-kiosk-orders/', views.search_kiosk_orders, name='search_kiosk_orders'),
    path('api/kiosk-order-items/<int:order_id>/', views.kiosk_order_items, name='kiosk_order_items'),
    path('api/debug-kiosk-orders/', views.debug_kiosk_orders, name='debug_kiosk_orders'),
    
    # Debug routes
    path('debug-user-status/', views.debug_user_status, name='debug_user_status'),
    path('debug-registration-test/', views.debug_registration_test, name='debug_registration_test'),
    path('debug-database/', views.debug_database_state, name='debug_database_state'),
    path('debug-all-staff/', views.debug_all_staff, name='debug_all_staff'),
    path('debug-search/', views.debug_search, name='debug_search'),
    path('debug-sales-search/', views.debug_sales_search, name='debug_sales_search'),
    path('debug-void-system/', views.debug_void_system, name='debug_void_system'),
    path('debug-void/<int:order_id>/', views.debug_void_process, name='debug_void_process'),
    path('test-static/', views.test_static, name='test_static'),
    path('test-auth/', views.test_auth, name='test_auth'),
    path('debug-auth/', views.debug_auth, name='debug_auth'),
    path('test-data/', views.test_data, name='test_data'),
    path('debug-urls/', views.debug_urls, name='debug_urls'),
    path('debug-csrf/', views.debug_csrf_issue, name='debug_csrf'),
    path('debug-form-data/', views.debug_form_data, name='debug_form_data'),
    path('debug-kiosk-orders/', views.debug_kiosk_orders, name='debug_kiosk_orders'),
    path('debug-redirects/', views.debug_redirects, name='debug_redirects'),
    path('staff-dashboard/debug/', views.staff_dashboard_debug, name='staff_dashboard_debug'),
    path('debug-user-status/', views.debug_user_status, name='debug_user_status'),

    # Real-time dashboard URLs
    path('staff-dashboard/realtime-data/', views.staff_dashboard_realtime_data, name='staff_dashboard_realtime_data'),
    path('staff-dashboard/new-orders-check/', views.staff_new_orders_check, name='staff_new_orders_check'),
    path('sales-report/realtime-data/', views.sales_report_realtime_data, name='sales_report_realtime_data'),
    path('sales-report/new-orders-check/', views.sales_report_new_orders_check, name='sales_report_new_orders_check'),

    # Payment processing URLs
    path('pay/redirect/<str:method>/<int:order_id>/', views.payment_redirect, name='payment_redirect'),
    path('cash-reconciliation/', views.cash_reconciliation_report, name='cash_reconciliation_report'),
    path('delete-adjustment/<int:adjustment_id>/', views.delete_adjustment, name='delete_adjustment'),
    path('check-cash-fields/', views.check_cash_fields, name='check_cash_fields'),
]