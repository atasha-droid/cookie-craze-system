from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from .models import Staff

def staff_required(view_func):
    """Simple decorator for staff permissions"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('home')
        if not request.user.is_staff and not hasattr(request.user, 'staff'):
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_required(view_func):
    """Decorator for admin-only views"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('home')
        if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

def customer_required(view_func):
    """Decorator for customer-only views"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('customer_login')
        if not hasattr(request.user, 'profile') or request.user.profile.user_type != 'customer':
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

def is_approved_staff(user):
    """Check if user is approved staff"""
    if user.is_superuser:
        return True
    try:
        if hasattr(user, 'staff'):
            return user.staff.is_active and user.staff.role != 'pending'
    except:
        pass
    return False

def is_admin_user(user):
    """Check if user is admin"""
    if user.is_superuser:
        return True
    if hasattr(user, 'staff'):
        return user.staff.role == 'admin'
    return False