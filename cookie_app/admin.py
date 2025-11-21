from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import Order, OrderItem, Cookie, Customer, Staff, Category, ActivityLog, VoidLog, UserProfile

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['cookie', 'quantity', 'price', 'total_price_display']
    can_delete = False
    
    def total_price_display(self, obj):
        return f"₱{obj.total_price:.2f}"
    total_price_display.short_description = 'Total'

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_id', 
        'customer_name', 
        'get_staff_username',
        'total_amount_display', 
        'payment_method', 
        'order_type', 
        'status',
        'created_at'
    ]
    
    list_filter = [
        'order_type',
        'status', 
        'payment_method',
        'created_at',
        'staff'
    ]
    
    search_fields = [
        'order_id',
        'customer_name',
        'staff__username',
        'customer__name'
    ]
    
    readonly_fields = [
        'order_id',
        'created_at', 
        'updated_at',
        'completed_at',
        'paid_at'
    ]
    
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': (
                'order_id', 
                'order_type', 
                'status',
                'total_amount',
                'payment_method',
                'notes',
                'is_paid'
            )
        }),
        ('Customer Information', {
            'fields': (
                'customer',
                'customer_name',
                'customer_phone',
            )
        }),
        ('Staff Information', {
            'fields': (
                'staff',
            )
        }),
        ('Daily Report', {
            'fields': (
                'is_daily_report',
                'report_date',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
                'paid_at',
                'completed_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def get_staff_username(self, obj):
        return obj.staff.username if obj.staff else 'N/A'
    get_staff_username.short_description = 'Recorded By'
    
    def total_amount_display(self, obj):
        return f"₱{obj.total_amount:.2f}"
    total_amount_display.short_description = 'Total Amount'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('customer', 'staff')

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'cookie', 'quantity', 'price_display', 'total_price_display']
    list_filter = ['cookie__flavor', 'order__order_type']
    search_fields = ['order__order_id', 'cookie__name']
    
    def price_display(self, obj):
        return f"₱{obj.price:.2f}"
    price_display.short_description = 'Price'
    
    def total_price_display(self, obj):
        return f"₱{obj.total_price:.2f}"
    total_price_display.short_description = 'Total'

@admin.register(Cookie)
class CookieAdmin(admin.ModelAdmin):
    list_display = ['name', 'flavor', 'price_display', 'stock_quantity', 'is_available', 'category']
    list_filter = ['flavor', 'is_available', 'category', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'flavor', 'price', 'description', 'category')
        }),
        ('Inventory', {
            'fields': ('stock_quantity', 'is_available')
        }),
        ('Media', {
            'fields': ('image',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def price_display(self, obj):
        return f"₱{obj.price:.2f}"
    price_display.short_description = 'Price'

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'loyalty_points', 'date_joined']
    list_filter = ['date_joined']
    search_fields = ['name', 'email', 'phone']
    readonly_fields = ['date_joined']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'get_cookie_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_cookie_count(self, obj):
        return obj.cookies.count()  # Use the relationship directly
    get_cookie_count.short_description = 'Cookie Count'

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['user', 'staff_id', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'date_joined']
    search_fields = ['user__username', 'staff_id']
    readonly_fields = ['date_joined']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'user_type', 'phone_number', 'date_joined']
    list_filter = ['user_type', 'date_joined']
    search_fields = ['user__username', 'customer_id', 'staff_id']
    readonly_fields = ['date_joined']

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'description', 'timestamp', 'ip_address']
    list_filter = ['action', 'timestamp', 'user']
    search_fields = ['user__username', 'description', 'ip_address']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'staff')

@admin.register(VoidLog)
class VoidLogAdmin(admin.ModelAdmin):
    list_display = ['void_id', 'order', 'staff_member', 'void_date']
    list_filter = ['void_date']
    search_fields = ['void_id', 'order__order_id']
    readonly_fields = ['void_date']

# Custom User Admin to show related orders
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ('get_recorded_orders_count',)
    
    def get_recorded_orders_count(self, obj):
        return obj.recorded_orders.count()
    get_recorded_orders_count.short_description = 'Orders Recorded'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('recorded_orders')

# Re-register User admin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)