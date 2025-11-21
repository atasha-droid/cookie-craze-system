# utils.py
from .models import ActivityLog

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def log_activity(user, action, description, ip_address=None, affected_model=None, affected_id=None):
    """Log user activity"""
    try:
        ActivityLog.objects.create(
            user=user,
            action=action,
            description=description,
            ip_address=ip_address,
            affected_model=affected_model,
            affected_id=affected_id
        )
    except Exception as e:
        # Log to console if database logging fails
        print(f"Activity log error: {e}")

def calculate_order_total(items):
    """Calculate total amount for order items"""
    total = 0
    for item in items:
        total += item['quantity'] * float(item['price'])
    return total

def update_cookie_stock(cookie, quantity_sold):
    """Update cookie stock quantity"""
    cookie.stock_quantity -= quantity_sold
    if cookie.stock_quantity < 0:
        cookie.stock_quantity = 0
    cookie.save()

def validate_stock_availability(cookie_id, quantity):
    """Validate if enough stock is available"""
    from .models import Cookie
    try:
        cookie = Cookie.objects.get(id=cookie_id)
        return cookie.stock_quantity >= quantity
    except Cookie.DoesNotExist:
        return False

def generate_receipt_data(order):
    """Generate receipt data for order"""
    receipt_data = {
        'order_id': order.order_id,
        'customer_name': order.customer_name or 'Walk-in Customer',
        'date': order.created_at.strftime('%Y-%m-%d %H:%M'),
        'items': [],
        'subtotal': 0,
        'total': float(order.total_amount),
        'payment_method': order.get_payment_method_display(),
        'staff_name': order.staff.get_full_name() if order.staff else 'Kiosk'
    }
    
    for item in order.items.all():
        item_data = {
            'name': item.cookie.name,
            'quantity': item.quantity,
            'price': float(item.price),
            'total': float(item.total_price)
        }
        receipt_data['items'].append(item_data)
        receipt_data['subtotal'] += item_data['total']
    
    return receipt_data

def generate_daily_report(staff, date):
    """Generate daily sales report for staff"""
    from .models import Order, OrderItem
    from django.db.models import Sum, Count
    
    orders = Order.objects.filter(
        staff=staff,
        created_at__date=date,
        status='completed'
    )
    
    report_data = {
        'staff_name': staff.user.get_full_name() or staff.user.username,
        'date': date,
        'total_orders': orders.count(),
        'total_sales': orders.aggregate(total=Sum('total_amount'))['total'] or 0,
        'orders_by_type': orders.values('order_type').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ),
        'top_items': OrderItem.objects.filter(
            order__in=orders
        ).values(
            'cookie__name'
        ).annotate(
            quantity_sold=Sum('quantity'),
            revenue=Sum('price')
        ).order_by('-quantity_sold')[:5]
    }
    
    return report_data

def is_approved_staff(user):
    """
    Check if a staff user is approved to access the system
    """
    try:
        if hasattr(user, 'profile'):
            # For staff and admin users, check if they are approved
            if user.profile.user_type in ['staff', 'admin']:
                # If user has staff_profile, check approval status
                if hasattr(user.profile, 'staff_profile'):
                    return user.profile.staff_profile.is_approved
                # If no staff_profile exists but user is staff/admin, assume approved for now
                # You might want to create a staff_profile in this case
                return True
        return False
    except Exception as e:
        print(f"Error checking staff approval: {e}")
        return False