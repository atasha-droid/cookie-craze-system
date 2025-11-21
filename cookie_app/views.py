from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.models import Group, User
from django.db.models import Sum, Count, Avg, Q, F
from django.db.models.functions import Extract
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from urllib.parse import quote
from django.db import models
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.csrf import ensure_csrf_cookie
from .filters import OrderFilter
from .models import CashFloat 

import json 
from django.http import JsonResponse, HttpResponse
from datetime import timedelta, datetime, time
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal, InvalidOperation
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Order, OrderItem, UserProfile, Category, Cookie, Customer, Staff, ActivityLog, VoidLog, StoreSettings, Branch
from .forms import WalkInOrderForm, CategoryForm, DailySalesForm, CustomerRegistrationForm, CustomerOrderForm, CustomerForm, CookieForm, SaleForm, StaffRegistrationForm, StaffEditForm, StoreSettingsForm
from .decorators import staff_required, admin_required
from .utils import log_activity, get_client_ip, calculate_order_total, update_cookie_stock, validate_stock_availability
import logging
import os
import glob
import csv
logger = logging.getLogger(__name__)

# ==================== PERMISSION FUNCTIONS ====================
def log_activity(user, action, description, ip_address=None, affected_model=None, affected_id=None):
    """Log user activity"""
    try:
        staff_instance = None
        if hasattr(user, 'staff'):
            staff_instance = user.staff
            
        ActivityLog.objects.create(
            user=user,
            staff=staff_instance,
            action=action,
            description=description,
            ip_address=ip_address,
            affected_model=affected_model,
            affected_id=affected_id
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

def is_approved_staff(user):
    """Simple check if user can access staff areas"""
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    try:
        if hasattr(user, 'staff'):
            return user.staff.is_active and user.staff.role != 'pending'
    except:
        pass
    
    return False

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def log_activity(user, action, description, ip_address=None):
    """Log user activity"""
    try:
        staff_instance = None
        if hasattr(user, 'staff'):
            staff_instance = user.staff
            
        ActivityLog.objects.create(
            user=user,
            staff=staff_instance,
            action=action,
            description=description,
            ip_address=ip_address
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

def is_admin_or_staff(user):
    """Check if user is admin (superuser or admin role)"""
    if not user.is_authenticated:
        return False
        
    if user.is_superuser:
        return True
    if hasattr(user, 'staff'):
        return user.staff.role in ['admin', 'staff'] and user.staff.is_active
    return False

def staff_required(view_func):
    """Simple decorator for staff permissions"""
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('home')
        if not is_approved_staff(request.user):
            return redirect('pending_approval')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def admin_required(view_func):
    """Decorator for admin permissions"""
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('home')
        if not is_admin_or_staff(request.user):
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def customer_required(view_func):
    """Decorator for customer-only permissions"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('home')
        if not hasattr(request.user, 'profile'):
            return redirect('dashboard')
        if request.user.profile.user_type != 'customer':
            return redirect('dashboard')
        if not hasattr(request.user.profile, 'customer'):
            # Redirect to staff/admin dashboard instead of home to avoid loops
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

# ==================== KIOSK ORDER SYSTEM ====================
def kiosk_order(request):
    """Kiosk order placement - no login required"""
    available_cookies = Cookie.objects.filter(stock_quantity__gt=0, is_available=True).select_related('category')
    
    # Group cookies by category
    categories = Category.objects.filter(cookies__in=available_cookies).distinct()
    cookies_by_category = {}
    
    for cookie in available_cookies:
        if cookie.category:
            category_name = cookie.category.name
        else:
            category_name = 'Other'
        
        if category_name not in cookies_by_category:
            cookies_by_category[category_name] = []
        cookies_by_category[category_name].append(cookie)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('items', [])
            customer_name = data.get('customer_name', '').strip()
            payment_method = data.get('payment_method', 'gcash')
            
            if not items:
                return JsonResponse({'success': False, 'error': 'No items in order'})
            
            # Calculate total and validate stock
            total_amount = Decimal('0.00')
            order_items = []
            
            for item in items:
                cookie_id = item.get('cookie_id')
                quantity = int(item.get('quantity', 0))
                
                if quantity > 0:
                    cookie = get_object_or_404(Cookie, id=cookie_id)
                    
                    if cookie.stock_quantity < quantity:
                        return JsonResponse({
                            'success': False, 
                            'error': f'Not enough stock for {cookie.name}. Only {cookie.stock_quantity} available.'
                        })
                    
                    item_total = cookie.price * quantity
                    total_amount += item_total
                    
                    order_items.append({
                        'cookie': cookie,
                        'quantity': quantity,
                        'price': cookie.price
                    })
            
            # Create kiosk order
            order = Order.objects.create(
                customer_name=customer_name or 'Kiosk Customer',
                order_type='kiosk',
                total_amount=total_amount,
                payment_method=payment_method,
                status='pending'
            )
            
            # Create order items
            for item_data in order_items:
                OrderItem.objects.create(
                    order=order,
                    cookie=item_data['cookie'],
                    quantity=item_data['quantity'],
                    price=item_data['price']
                )
                
                # Update stock
                cookie = item_data['cookie']
                cookie.stock_quantity -= item_data['quantity']
                cookie.save()
            
            log_activity(
                user=None,
                action='order_created',
                description=f'Kiosk order created: {order.order_id} - ₱{total_amount:.2f}',
                ip_address=get_client_ip(request),
                affected_model='Order',
                affected_id=order.id
            )
            
            return JsonResponse({
                'success': True,
                'order_id': order.order_id,
                'order_db_id': order.id,
                'total_amount': str(total_amount),
                'redirect_url': f'/app/kiosk/payment/{order.id}/'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return render(request, 'kiosk/order.html', {
        'available_cookies': available_cookies,
        'cookies_by_category': cookies_by_category,
        'categories': categories
    })


def kiosk_payment(request, order_id):
    """Kiosk payment processing with cash tracking"""
    order = get_object_or_404(Order, id=order_id, order_type='kiosk')
    
    if request.method == 'POST':
        try:
            payment_method = request.POST.get('payment_method', 'gcash')
            amount_paid = Decimal(request.POST.get('amount_paid', '0'))
            
            # Validate payment
            if amount_paid < order.total_amount:
                messages.error(request, f'Insufficient payment. Total: ₱{order.total_amount:.2f}')
                return redirect('kiosk_payment', order_id=order.id)
            
            # Store cash received for cash payments
            cash_received = amount_paid if payment_method == 'cash' else None
            
            # Complete the order
            order.status = 'completed'
            order.payment_method = payment_method
            order.is_paid = True
            order.paid_at = timezone.now()
            order.cash_received = cash_received  # NEW: Store cash received
            order.save()
            
            log_activity(
                user=None,
                action='order_completed',
                description=f'Kiosk order completed: {order.order_id} - ₱{order.total_amount:.2f} - Payment: {payment_method}',
                ip_address=get_client_ip(request),
                affected_model='Order',
                affected_id=order.id
            )
            
            messages.success(request, f'Payment successful! Order ID: {order.order_id}')
            if payment_method == 'cash':
                messages.info(request, f'Cash received: ₱{amount_paid:.2f} | Change: ₱{order.change:.2f}')
            
            return redirect('kiosk_receipt', order_id=order.id)
            
        except Exception as e:
            messages.error(request, f'Payment error: {str(e)}')
    
    return render(request, 'kiosk/payment.html', {
        'order': order
    })

def kiosk_receipt(request, order_id):
    """Kiosk order receipt"""
    order = get_object_or_404(Order, id=order_id, order_type='kiosk')
    return render(request, 'kiosk/receipt.html', {
        'order': order
    })

# ==================== STAFF ORDER SYSTEM ====================
@login_required
@staff_required
def staff_record_sale(request):
    """Staff record sale form - handles both walk-in and kiosk orders"""
    available_cookies = Cookie.objects.filter(stock_quantity__gt=0, is_available=True).select_related('category')
    customers = Customer.objects.all()
    
    # Group cookies by category
    categories = Category.objects.filter(cookies__in=available_cookies).distinct()
    cookies_by_category = {}
    
    for cookie in available_cookies:
        if cookie.category:
            category_name = cookie.category.name
        else:
            category_name = 'Other'
        
        if category_name not in cookies_by_category:
            cookies_by_category[category_name] = []
        cookies_by_category[category_name].append(cookie)
    
    if request.method == 'POST':
        try:
            order_type = request.POST.get('order_type', 'walkin')
            kiosk_order_id = request.POST.get('kiosk_order_id')
            
            print(f"=== FORM SUBMISSION DEBUG ===")
            print(f"Order Type: '{order_type}'")
            print(f"Kiosk Order ID: '{kiosk_order_id}'")
            print(f"Cash Received: '{request.POST.get('cash_received')}'")
            print(f"Amount Paid: '{request.POST.get('amount_paid')}'")
            
            # Handle kiosk order completion
            if order_type == 'kiosk':
                print("Processing kiosk order...")
                if kiosk_order_id and kiosk_order_id.strip() != '':
                    print(f"Kiosk order ID found: {kiosk_order_id}")
                    return complete_kiosk_order(request, kiosk_order_id)
                else:
                    print("ERROR: No kiosk order ID provided")
                    messages.error(request, 'Please select a kiosk order to complete the sale.')
                    return redirect('staff_record_sale')
            
            # Handle walk-in order creation
            elif order_type == 'walkin':
                print("Processing walk-in order...")
                return create_walkin_order(request, cookies_by_category)
            
            # If we get here, something went wrong
            print(f"ERROR: Invalid order type: {order_type}")
            messages.error(request, 'Invalid order type')
            return redirect('staff_record_sale')
            
        except Exception as e:
            print(f"EXCEPTION: {str(e)}")
            import traceback
            traceback.print_exc()
            messages.error(request, f'Error recording sale: {str(e)}')
            return redirect('staff_record_sale')
    
    return render(request, 'record_sale.html', {
        'available_cookies': available_cookies,
        'customers': customers,
        'cookies_by_category': cookies_by_category,
        'categories': categories
    })

def create_walkin_order(request, cookies_by_category):
    """Create a new walk-in order with cash payment tracking"""
    print("=== CREATE WALKIN ORDER DEBUG ===")
    print(f"POST data: {dict(request.POST)}")
    
    customer_id = request.POST.get('customer_id')
    customer_name = request.POST.get('customer_name', '').strip()
    customer_phone = request.POST.get('customer_phone', '')
    payment_method = request.POST.get('payment_method', 'cash')
    notes = request.POST.get('notes', '')
    
    # Get cash payment details
    cash_received = None
    amount_paid = request.POST.get('amount_paid')
    
    if payment_method == 'cash' and amount_paid:
        try:
            cash_received = Decimal(amount_paid)
            print(f"Cash received: ₱{cash_received}")
        except (ValueError, TypeError):
            cash_received = None
    
    # Process items - look for cookie quantities
    total_amount = Decimal('0.00')
    order_items = []
    
    # Debug: Check all POST data for cookies
    print("=== COOKIE DATA SEARCH ===")
    for key, value in request.POST.items():
        print(f"POST key: {key} = {value}")
        if key.startswith('cookie_') and value.isdigit():
            cookie_id = key.replace('cookie_', '')
            quantity = int(value)
            
            if quantity > 0:
                print(f"Found cookie with quantity: ID={cookie_id}, Qty={quantity}")
                try:
                    cookie = Cookie.objects.get(id=cookie_id)
                    
                    if cookie.stock_quantity < quantity:
                        messages.error(request, f'Not enough stock for {cookie.name}. Only {cookie.stock_quantity} available.')
                        return redirect('staff_record_sale')
                    
                    item_total = cookie.price * quantity
                    total_amount += item_total
                    
                    order_items.append({
                        'cookie': cookie,
                        'quantity': quantity,
                        'price': cookie.price
                    })
                    print(f"Added to order: {cookie.name} x {quantity} = ₱{item_total}")
                    
                except Cookie.DoesNotExist:
                    print(f"Cookie with ID {cookie_id} not found")
                    continue
    
    # Validate cookies for walk-in orders
    if not order_items:
        messages.error(request, 'Please select at least one item for walk-in order')
        return redirect('staff_record_sale')
    
    # Payment validation rules
    if payment_method == 'cash':
        # Require amount_paid and ensure it's >= total
        if amount_paid is None or str(amount_paid).strip() == '':
            messages.error(request, 'Please enter Cash Amount Paid.')
            return redirect('staff_record_sale')
        if cash_received is None or cash_received < total_amount:
            messages.error(request, f'Insufficient cash received. Total: ₱{total_amount:.2f}, Received: ₱{(cash_received or Decimal("0.00")):.2f}')
            return redirect('staff_record_sale')
    elif payment_method == 'gcash':
        # Require GCash number and reference at creation time
        gcash_number = (request.POST.get('gcash_number') or '').strip()
        gcash_reference = (request.POST.get('gcash_reference') or '').strip()
        if not gcash_number or not gcash_reference:
            messages.error(request, 'Please enter both GCash Number and Reference Number.')
            return redirect('staff_record_sale')
    
    print(f"Total items: {len(order_items)}")
    print(f"Total amount: {total_amount}")
    print(f"Cash received: {cash_received}")
    
    # Get customer
    customer = None
    print(f"=== CUSTOMER MATCHING DEBUG ===")
    print(f"customer_id: {customer_id}")
    print(f"customer_name: {customer_name}")
    print(f"customer_phone: {customer_phone}")
    
    if customer_id:
        print(f"Looking up customer by ID: {customer_id}")
        customer = get_object_or_404(Customer, id=customer_id)
        print(f"Found customer by ID: {customer.name} ({customer.id})")
    else:
        # Auto-link to existing customer by name or phone if possible
        if customer_name or customer_phone:
            name = customer_name.strip() if customer_name else ''
            phone = customer_phone.strip() if customer_phone else ''
            
            print(f"Searching for customer with name: '{name}', phone: '{phone}'")
            
            # Try to find exact match first
            if name and phone:
                customer = Customer.objects.filter(
                    models.Q(name__iexact=name) & 
                    models.Q(phone__iexact=phone)
                ).first()
                
            # If no exact match, try partial matches
            if not customer and (name or phone):
                lookup_q = models.Q()
                if name:
                    lookup_q |= models.Q(name__iexact=name)
                if phone:
                    lookup_q |= models.Q(phone__iexact=phone)
                
                customer = Customer.objects.filter(lookup_q).order_by(
                    '-date_joined'  # Most recent customers first
                ).first()
            
            if customer:
                print(f"✅ Auto-linked walk-in order to customer: {customer.name} (ID: {customer.id})")
                print(f"    Email: {customer.email}, Phone: {customer.phone}")
            else:
                print("ℹ️ No matching customer found - order will be recorded without customer association")
    
    print(f"Final customer: {customer}")
    print("=== END CUSTOMER MATCHING ===")
    
    # Create staff order depending on payment method
    if payment_method == 'cash':
        order = Order.objects.create(
            customer=customer,
            customer_name=customer_name or (customer.name if customer else 'Walk-in Customer'),
            customer_phone=customer_phone or (customer.phone if customer else ''),
            staff=request.user,
            order_type='staff',
            total_amount=total_amount,
            payment_method='cash',
            status='completed',
            is_paid=True,
            paid_at=timezone.now(),
            notes=notes,
            cash_received=cash_received,
        )
    else:  # gcash
        order = Order.objects.create(
            customer=customer,
            customer_name=customer_name or (customer.name if customer else 'Walk-in Customer'),
            customer_phone=customer_phone or (customer.phone if customer else ''),
            staff=request.user,
            order_type='staff',
            total_amount=total_amount,
            payment_method='gcash',
            status='pending',
            is_paid=False,
            notes=notes,
            gcash_reference=gcash_reference,
        )
    
    print(f"Order created: {order.order_id} with status: {order.status}")
    print(f"Cash received stored: {order.cash_received}")
    print(f"Change calculated: {order.change}")
    
    # Create order items
    for item_data in order_items:
        OrderItem.objects.create(
            order=order,
            cookie=item_data['cookie'],
            quantity=item_data['quantity'],
            price=item_data['price']
        )
        
        # Update stock
        cookie = item_data['cookie']
        cookie.stock_quantity -= item_data['quantity']
        cookie.save()
        print(f"Updated stock for {cookie.name}: -{item_data['quantity']}")
    
    # Add loyalty points for registered customers
    if customer:
        points_earned = int(total_amount)
        customer.loyalty_points += points_earned
        customer.save()
        print(f"Added {points_earned} loyalty points to customer {customer.name}")
    
    log_activity(
        user=request.user,
        action='order_created',
        description=(
            f'Staff order created: {order.order_id} - ₱{total_amount:.2f} - '
            f'Payment: {payment_method.upper()} - Cash: ₱{(cash_received or Decimal("0.00")):.2f}'
        ),
        ip_address=get_client_ip(request),
        affected_model='Order',
        affected_id=order.id
    )
    
    # Redirect appropriately
    if payment_method == 'cash':
        return redirect('staff_order_receipt', order_id=order.id)
    else:
        messages.success(request, f'Order {order.order_id} created. Please verify GCash payment to complete the order.')
        return redirect('order_management')

def complete_kiosk_order(request, kiosk_order_id):
    """Complete a pending kiosk order with cash payment tracking"""
    try:
        kiosk_order = get_object_or_404(Order, id=kiosk_order_id, order_type='kiosk', status='pending')
        
        print(f"=== COMPLETING KIOSK ORDER ===")
        print(f"Order: {kiosk_order.order_id}")
        print(f"Current status: {kiosk_order.status}")
        
        # Get cash payment details for kiosk orders
        cash_received = None
        amount_paid = request.POST.get('amount_paid')
        payment_method = request.POST.get('payment_method', kiosk_order.payment_method)
        
        if payment_method == 'cash' and amount_paid:
            try:
                cash_received = Decimal(amount_paid)
                if cash_received < kiosk_order.total_amount:
                    messages.error(request, f'Insufficient cash received. Total: ₱{kiosk_order.total_amount:.2f}, Received: ₱{cash_received:.2f}')
                    return redirect('staff_record_sale')
                print(f"Cash received for kiosk order: ₱{cash_received}")
            except (ValueError, TypeError):
                cash_received = None
        
        # Update kiosk order status to completed
        kiosk_order.status = 'completed'
        kiosk_order.is_paid = True
        kiosk_order.paid_at = timezone.now()
        kiosk_order.completed_at = timezone.now()
        kiosk_order.staff = request.user  # Record which staff completed the order
        kiosk_order.payment_method = payment_method
        kiosk_order.cash_received = cash_received  # NEW: Store cash received
        kiosk_order.save()
        
        print(f"Updated status to: {kiosk_order.status}")
        print(f"Is paid: {kiosk_order.is_paid}")
        print(f"Cash received stored: {kiosk_order.cash_received}")
        print(f"Change calculated: {kiosk_order.change}")
        
        # Update inventory for kiosk order items
        for item in kiosk_order.items.all():
            cookie = item.cookie
            if cookie.stock_quantity >= item.quantity:
                cookie.stock_quantity -= item.quantity
                cookie.save()
                print(f"Updated stock for {cookie.name}: -{item.quantity}")
            else:
                messages.warning(request, f'Insufficient stock for {cookie.name}. Order completed but inventory not updated.')
        
        # Add loyalty points if customer exists
        if kiosk_order.customer:
            points_earned = int(kiosk_order.total_amount)
            kiosk_order.customer.loyalty_points += points_earned
            kiosk_order.customer.save()
            print(f"Added {points_earned} loyalty points to customer")
        
        log_activity(
            user=request.user,
            action='order_completed',
            description=f'Kiosk order completed: {kiosk_order.order_id} - ₱{kiosk_order.total_amount:.2f} - Cash: ₱{cash_received or 0:.2f} - Change: ₱{kiosk_order.change or 0:.2f}',
            ip_address=get_client_ip(request),
            affected_model='Order',
            affected_id=kiosk_order.id
        )
        
        messages.success(request, f'Kiosk order completed successfully! Order ID: {kiosk_order.order_id}')
        if payment_method == 'cash' and cash_received:
            messages.info(request, f'Cash received: ₱{cash_received:.2f} | Change: ₱{kiosk_order.change:.2f}')
        
        return redirect('staff_order_receipt', order_id=kiosk_order.id)
        
    except Order.DoesNotExist:
        messages.error(request, 'Kiosk order not found or already completed')
        return redirect('staff_record_sale')
    except Exception as e:
        messages.error(request, f'Error completing kiosk order: {str(e)}')
        return redirect('staff_record_sale')

@login_required
@staff_required
def staff_order_receipt(request, order_id):
    """Staff order receipt"""
    order = get_object_or_404(Order, id=order_id)
    # Prevent printing for unverified GCash payments
    if order.payment_method == 'gcash' and not order.is_paid:
        messages.error(request, 'GCash payment not yet verified. Verify payment to print the receipt.')
        return redirect('order_management')
    return render(request, 'staff/order_receipt.html', {
        'order': order
    })

# ==================== ORDER MANAGEMENT ====================
@login_required
@staff_required
def order_list(request):
    # Start with all orders
    orders = Order.objects.all().order_by('-created_at')
    
    # Manual filtering based on GET parameters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    order_type_filter = request.GET.get('order_type', '')
    payment_method_filter = request.GET.get('payment_method', '')
    
    # Apply search filter
    if search_query:
        orders = orders.filter(
            models.Q(order_id__icontains=search_query) |
            models.Q(customer_name__icontains=search_query) |
            models.Q(hex_id__icontains=search_query)
        )
    
    # Apply status filter
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    # Apply order type filter
    if order_type_filter:
        orders = orders.filter(order_type=order_type_filter)
    
    # Apply payment method filter
    if payment_method_filter:
        orders = orders.filter(payment_method=payment_method_filter)
    
    # Debug information
    print(f"=== MANUAL FILTER DEBUG ===")
    print(f"Search: '{search_query}'")
    print(f"Status: '{status_filter}'")
    print(f"Order Type: '{order_type_filter}'")
    print(f"Payment Method: '{payment_method_filter}'")
    print(f"Total orders: {orders.count()}")
    
    # Still use the filter for form rendering, but with the filtered queryset
    order_filter = OrderFilter(request.GET, queryset=orders)
    
    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'filter': order_filter
    })

@login_required
@staff_required
@require_POST
def verify_gcash(request, order_id: int):
    """Manual GCash verification: store reference/amount, mark order as paid and completed."""
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.payment_method != 'gcash':
            return JsonResponse({'success': False, 'error': 'Payment method is not GCash.'}, status=400)

        # Basic CSRF is enforced by @require_POST and Django middleware; this endpoint expects AJAX too
        ref = (request.POST.get('gcash_reference') or '').strip()
        amount_str = (request.POST.get('gcash_amount') or '').strip()
        if not ref or not amount_str:
            return JsonResponse({'success': False, 'error': 'Reference and amount are required.'}, status=400)
        try:
            amt = Decimal(amount_str)
        except Exception:
            return JsonResponse({'success': False, 'error': 'Invalid amount.'}, status=400)
        if amt < order.total_amount:
            return JsonResponse({'success': False, 'error': 'Amount does not match the total bill.'}, status=400)
        now = timezone.now()
        order.gcash_reference = ref
        order.gcash_amount = amt
        order.gcash_verified_by = request.user
        order.gcash_verified_at = now
        order.is_paid = True
        order.paid_at = now
        # After payment verification, move order into preparing stage
        order.status = 'preparing'
        order.save()

        log_activity(
            user=request.user,
            action='gcash_verified',
            description=f'Order {order.order_id} verified via GCash (ref {ref}).',
            ip_address=get_client_ip(request)
        )

        return JsonResponse({'success': True, 'message': 'GCash payment verified and order moved to Preparing.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'}, status=500)

@login_required
@staff_required
def order_management(request):
    """Order Management hub - FIXED VERSION"""
    user = request.user
    is_admin = user.is_superuser or (hasattr(user, 'staff') and user.staff.role == 'admin')

    # Base queryset - include all orders for admin, appropriate scope for staff
    if is_admin:
        qs = Order.objects.select_related('customer', 'staff', 'branch').prefetch_related('items__cookie').order_by('-created_at')
    else:
        # Staff can see:
        # 1. Orders they recorded
        # 2. Kiosk orders (staff__isnull=True) 
        # 3. From any date (not just today)
        qs = Order.objects.select_related('customer', 'staff', 'branch').prefetch_related('items__cookie').filter(
            models.Q(staff=user) | models.Q(staff__isnull=True)
        ).order_by('-created_at')

    # Common filters for both admin and staff
    search = (request.GET.get('search') or '').strip()
    status = (request.GET.get('status') or '').strip()
    payment_method = (request.GET.get('payment') or '').strip()

    if search:
        qs = qs.filter(
            models.Q(order_id__icontains=search) |
            models.Q(customer_name__icontains=search) |
            models.Q(customer__user_profile__user__username__icontains=search) |
            models.Q(staff__username__icontains=search) |
            models.Q(hex_id__icontains=search) |
            models.Q(gcash_reference__icontains=search)
        )
    
    if status and status != 'all':
        qs = qs.filter(status=status)
    
    if payment_method and payment_method != 'all':
        qs = qs.filter(payment_method=payment_method)

    # Admin-only filters
    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()
    staff_id = (request.GET.get('staff_id') or '').strip()
    branch_id = (request.GET.get('branch_id') or '').strip()
    
    if is_admin:
        if staff_id:
            qs = qs.filter(staff__id=staff_id)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                qs = qs.filter(created_at__date__gte=start_date)
            except ValueError:
                start_date_str = ''
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                qs = qs.filter(created_at__date__lte=end_date)
            except ValueError:
                end_date_str = ''

    # Apply reasonable limits
    orders = qs[:500]  # Increased limit to show more orders

    # Staff history: include their completed and cancelled orders
    staff_completed_orders = Order.objects.filter(
        staff=user,
        status__in=['completed', 'cancelled']
    ).select_related('customer').order_by('-completed_at')[:50] if not is_admin else None

    context = {
        'orders_today': orders,
        'staff_completed_orders': staff_completed_orders,
        'filter_values': {
            'search': search,
            'status': status,
            'payment': payment_method,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'staff_id': staff_id,
            'branch_id': branch_id,
            'is_admin': is_admin,
        },
        'all_staff': User.objects.filter(
            models.Q(is_staff=True) | models.Q(staff__is_active=True)
        ).distinct() if is_admin else None,
        'all_branches': Branch.objects.filter(is_active=True) if is_admin else None,
    }

    return render(request, 'orders/order_management.html', context)


@login_required
@admin_required
def admin_order_detail(request, order_id):
    """Admin-only detailed view for an order with activity log snippet."""
    order = get_object_or_404(
        Order.objects.select_related('customer', 'staff').prefetch_related('items__cookie'),
        id=order_id,
    )

    # Recent activity logs affecting this order
    activity = ActivityLog.objects.filter(
        affected_model='Order',
        affected_id=order.id,
    ).order_by('-timestamp')[:20]

    return render(request, 'admin/order_detail.html', {
        'order': order,
        'activity_logs': activity,
    })

@login_required
@staff_required
@require_POST
def confirm_cash_staff(request, order_id: int):
    """Staff confirms cash payment: amount must be provided; marks order paid+completed."""
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.payment_method != 'cash':
            return JsonResponse({'success': False, 'error': 'Payment method is not Cash.'}, status=400)
        amt_str = (request.POST.get('amount') or '').strip()
        if not amt_str:
            return JsonResponse({'success': False, 'error': 'Amount is required.'}, status=400)
        try:
            amt = Decimal(amt_str)
        except Exception:
            return JsonResponse({'success': False, 'error': 'Invalid amount.'}, status=400)
        if amt < order.total_amount:
            return JsonResponse({'success': False, 'error': 'Amount received is less than total.'}, status=400)
        now = timezone.now()
        order.cash_received = amt
        order.is_paid = True
        order.paid_at = now
        order.status = 'completed'
        order.completed_at = now
        order.save()
        log_activity(user=request.user, action='cash_confirmed', description=f'Cash payment confirmed for {order.order_id} amount ₱{amt}', ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': 'Cash payment confirmed and order completed.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'}, status=500)

@login_required
@staff_required
def staff_notifications(request):
    return render(request, 'staff/notifications.html', {})

@login_required
@staff_required
def update_order_status(request, order_id):
    """Update order status (AJAX)"""
    print(f"=== UPDATE ORDER STATUS REQUEST ===")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    print(f"POST data: {dict(request.POST)}")
    print(f"Order ID: {order_id}")
    print(f"User: {request.user}")
    
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            order = get_object_or_404(Order, id=order_id)
            new_status = request.POST.get('status')
            
            print(f"Current status: {order.status}")
            print(f"New status: {new_status}")
            
            if new_status in dict(Order.STATUS_CHOICES):
                old_status = order.status
                
                # Enforce valid transitions for staff
                valid_transitions = {
                    'pending': ['preparing', 'ready', 'completed'],
                    'preparing': ['ready', 'completed'],
                    'ready': ['completed'],
                    'completed': [],
                    'voided': [],
                    'cancelled': []
                }

                is_admin = request.user.is_superuser or (hasattr(request.user, 'staff') and request.user.staff.role == 'admin')
                if not is_admin:
                    allowed = valid_transitions.get(old_status, [])
                    if new_status not in allowed:
                        return JsonResponse({'success': False, 'error': f'Invalid transition: {old_status} → {new_status}'})

                order.status = new_status
                
                if new_status == 'completed':
                    order.is_paid = True
                    if not order.paid_at:
                        order.paid_at = timezone.now()
                
                order.save()
                
                log_activity(
                    user=request.user,
                    action='order_updated',
                    description=f'Order {order.order_id} status changed: {old_status} → {order.status}',
                    ip_address=get_client_ip(request),
                    affected_model='Order',
                    affected_id=order.id
                )
                
                return JsonResponse({
                    'success': True,
                    'message': f'Order status updated to {order.get_status_display()}',
                    'new_status': order.status,
                    'status_display': order.get_status_display()
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'error': f'Invalid status: {new_status}'
                })
                
        except Exception as e:
            print(f"Error updating order status: {str(e)}")
            return JsonResponse({
                'success': False, 
                'error': f'Server error: {str(e)}'
            })
    
    print("Invalid request - not AJAX or not POST")
    return JsonResponse({
        'success': False, 
        'error': 'Invalid request'
    })

# ==================== REPORTING ====================
@login_required
@staff_required
def sales_report(request):
    """Sales report with comprehensive cash payment statistics"""
    # Date filtering
    today = timezone.now().date()
    start_date = request.GET.get('start_date', today.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today
        end_date = today
    
    # Adjust end_date to include the entire day
    end_date_time = datetime.combine(end_date, time.max)
    
    # Get completed orders within date range
    completed_orders = Order.objects.filter(
        status='completed',
        created_at__date__range=[start_date, end_date]
    ).select_related('customer').prefetch_related('items', 'items__cookie')
    
    # Total sales statistics
    total_sales = completed_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Order type breakdown
    walkin_orders = completed_orders.filter(order_type='staff')
    kiosk_orders = completed_orders.filter(order_type='kiosk')
    
    order_type_stats = {
        'walkin': {
            'count': walkin_orders.count(),
            'revenue': walkin_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
            'avg_order': walkin_orders.aggregate(avg=Avg('total_amount'))['avg'] or 0
        },
        'kiosk': {
            'count': kiosk_orders.count(),
            'revenue': kiosk_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
            'avg_order': kiosk_orders.aggregate(avg=Avg('total_amount'))['avg'] or 0
        }
    }
    
    # Completion statistics
    all_orders = Order.objects.filter(created_at__date__range=[start_date, end_date])
    completion_stats = {
        'total_orders': all_orders.count(),
        'completed_orders': completed_orders.count(),
        'completion_rate': (completed_orders.count() / all_orders.count() * 100) if all_orders.count() > 0 else 0
    }
    
    # Cash payment statistics
    cash_orders = completed_orders.filter(payment_method='cash')
    total_cash_received = cash_orders.aggregate(total=Sum('cash_received'))['total'] or 0
    total_change_given = cash_orders.aggregate(total=Sum('change'))['total'] or 0
    
    cash_stats = {
        'count': cash_orders.count(),
        'amount': cash_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
        'cash_received': total_cash_received,
        'change_given': total_change_given,
        'percentage': (cash_orders.count() / completed_orders.count() * 100) if completed_orders.count() > 0 else 0,
        'avg_cash_received': cash_orders.aggregate(avg=Avg('cash_received'))['avg'] or 0,
        'avg_change': cash_orders.aggregate(avg=Avg('change'))['avg'] or 0
    }
    
    # Digital payment statistics
    digital_orders = completed_orders.exclude(payment_method='cash')
    digital_stats = {
        'count': digital_orders.count(),
        'amount': digital_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
        'percentage': (digital_orders.count() / completed_orders.count() * 100) if completed_orders.count() > 0 else 0
    }
    
    # Enhanced payment breakdown with percentages
    payment_breakdown = []
    for method in Order.PAYMENT_METHODS:
        method_orders = completed_orders.filter(payment_method=method[0])
        count = method_orders.count()
        amount = method_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        percentage = (count / completed_orders.count() * 100) if completed_orders.count() > 0 else 0
        
        # Add cash-specific metrics
        cash_specific = {}
        if method[0] == 'cash':
            cash_specific = {
                'total_cash_received': total_cash_received,
                'total_change_given': total_change_given,
                'avg_cash_received': cash_stats['avg_cash_received'],
                'avg_change': cash_stats['avg_change']
            }
        
        payment_breakdown.append({
            'payment_method': method[1],
            'method_code': method[0],
            'count': count,
            'amount': amount,
            'percentage': percentage,
            **cash_specific
        })
    
    # Daily sales breakdown
    daily_sales = completed_orders.values('completed_at__date').annotate(
        daily_total=Sum('total_amount'),
        order_count=Count('id'),
        walkin_count=Count('id', filter=Q(order_type='staff')),
        kiosk_count=Count('id', filter=Q(order_type='kiosk')),
        average_sale=Avg('total_amount')
    ).order_by('-completed_at__date')
    
    # Top selling cookies
    top_cookies = OrderItem.objects.filter(
        order__in=completed_orders
    ).values(
        'cookie__name'
    ).annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum('price')
    ).order_by('-total_sold')[:10]
    
    # Cash reconciliation summary
    cash_reconciliation = {
        'total_cash_sales': cash_stats['amount'],
        'total_cash_received': total_cash_received,
        'total_change_given': total_change_given,
        'net_cash_should_be': cash_stats['amount'],  # Should equal total sales amount
        'cash_handling_fee': total_change_given,  # Change given represents cash out
        'expected_cash_drawer': total_cash_received - total_change_given
    }
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'total_sales': total_sales,
        'order_type_stats': order_type_stats,
        'completion_stats': completion_stats,
        'cash_stats': cash_stats,
        'digital_stats': digital_stats,
        'payment_breakdown': payment_breakdown,
        'daily_sales': daily_sales,
        'top_cookies': top_cookies,
        'cash_reconciliation': cash_reconciliation,
        'today': today,
    }
    
    return render(request, 'sales_report.html', context)

@login_required
@staff_required
def cash_reconciliation_report(request):
    """Enhanced automated cash reconciliation with detailed transaction tracking"""
    today = timezone.now().date()
    
    # Get all today's cash-related data
    cash_floats = CashFloat.objects.filter(date=today).order_by('created_at')
    cash_orders = Order.objects.filter(
        created_at__date=today,
        payment_method='cash',
        status='completed',
        is_paid=True
    ).select_related('staff', 'customer')
    
    # Calculate starting cash (opening float)
    opening_float = cash_floats.filter(float_type='opening').first()
    starting_cash = opening_float.amount if opening_float else Decimal('0.00')
    
    # Calculate change used (additional change + change adjustments)
    additional_change = cash_floats.filter(
        float_type='additional'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    change_adjustments = cash_floats.filter(
        float_type='adjustment',
        adjustment_type__in=['change_add', 'change_remove']
    ).aggregate(
        change_added=Sum('amount', filter=Q(adjustment_type='change_add')),
        change_removed=Sum('amount', filter=Q(adjustment_type='change_remove'))
    )
    
    change_added = change_adjustments['change_added'] or Decimal('0.00')
    change_removed = change_adjustments['change_removed'] or Decimal('0.00')
    net_change_adjustments = change_added - change_removed
    change_used = additional_change + net_change_adjustments
    
    # Calculate cash sales from completed cash orders today
    cash_sales = cash_orders.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    # Calculate total cash received and change given
    cash_received_data = cash_orders.aggregate(
        total_cash_received=Sum('cash_received'),
        total_change_given=Sum('change')
    )
    
    total_cash_received = cash_received_data['total_cash_received'] or Decimal('0.00')
    total_change_given = cash_received_data['total_change_given'] or Decimal('0.00')
    
    # Get closing balance if exists
    closing_balance = cash_floats.filter(float_type='closing').first()
    amount_returned = closing_balance.amount if closing_balance else Decimal('0.00')
    
    # Calculate expected return and variance
    expected_return = starting_cash + cash_sales - change_used
    variance = amount_returned - expected_return if amount_returned else Decimal('0.00')
    shortage = -variance if variance < 0 else Decimal('0.00')
    overage = variance if variance > 0 else Decimal('0.00')
    
    # Prepare transaction details for the template
    cash_transactions = []
    
    # Add opening float transaction
    if opening_float:
        cash_transactions.append({
            'time': opening_float.created_at,
            'type': 'opening_float',
            'description': 'Opening Cash Float',
            'amount': opening_float.amount,
            'staff': opening_float.staff,
            'notes': opening_float.notes,
            'is_float': True
        })
    
    # Add additional change transactions
    for change in cash_floats.filter(float_type='additional'):
        cash_transactions.append({
            'time': change.created_at,
            'type': 'additional_change',
            'description': 'Additional Change Added',
            'amount': change.amount,
            'staff': change.staff,
            'notes': change.notes,
            'is_float': True
        })
    
    # Add cash sales transactions
    for order in cash_orders:
        cash_transactions.append({
            'time': order.paid_at or order.created_at,
            'type': 'cash_sale',
            'description': f'Cash Sale - {order.customer_name or "Walk-in"}',
            'amount': order.total_amount,
            'staff': order.staff,
            'notes': f'Order {order.order_id}',
            'order_id': order.order_id,
            'cash_received': order.cash_received,
            'change_given': order.change,
            'is_sale': True
        })
    
    # Add change adjustment transactions
    for adjustment in cash_floats.filter(float_type='adjustment'):
        adj_type = adjustment.get_adjustment_type_display()
        cash_transactions.append({
            'time': adjustment.created_at,
            'type': 'adjustment',
            'description': f'Cash Adjustment - {adj_type}',
            'amount': adjustment.amount,
            'staff': adjustment.staff,
            'notes': adjustment.notes,
            'adjustment_type': adjustment.adjustment_type,
            'is_float': True
        })
    
    # Add closing balance transaction
    if closing_balance:
        cash_transactions.append({
            'time': closing_balance.created_at,
            'type': 'closing_balance',
            'description': 'Closing Balance',
            'amount': closing_balance.amount,
            'staff': closing_balance.staff,
            'notes': closing_balance.notes,
            'is_float': True
        })
    
    # Sort transactions by time
    cash_transactions.sort(key=lambda x: x['time'])
    
    # Handle POST for manual overrides and closing balance
    manual_override = False
    if request.method == 'POST':
        try:
            if request.POST.get('manual_override') == 'true':
                manual_override = True
                starting_cash = Decimal(request.POST.get('starting_cash', '0') or '0')
                change_used = Decimal(request.POST.get('change_used', '0') or '0')
                cash_sales = Decimal(request.POST.get('cash_sales', '0') or '0')
                amount_returned = Decimal(request.POST.get('amount_returned', '0') or '0')
                
                expected_return = starting_cash + cash_sales - change_used
                variance = amount_returned - expected_return
                shortage = -variance if variance < 0 else Decimal('0.00')
                overage = variance if variance > 0 else Decimal('0.00')
                
                messages.info(request, 'Using manual override values')
            else:
                # Save closing balance if provided
                closing_amount = request.POST.get('closing_amount')
                if closing_amount:
                    closing_amount = Decimal(closing_amount)
                    # Create or update closing balance
                    closing_float, created = CashFloat.objects.get_or_create(
                        date=today,
                        float_type='closing',
                        defaults={
                            'amount': closing_amount,
                            'staff': request.user,
                            'notes': 'Closing balance from cash reconciliation'
                        }
                    )
                    if not created:
                        closing_float.amount = closing_amount
                        closing_float.staff = request.user
                        closing_float.notes = 'Closing balance updated from cash reconciliation'
                        closing_float.save()
                    
                    amount_returned = closing_amount
                    # Recalculate with updated closing balance
                    expected_return = starting_cash + cash_sales - change_used
                    variance = amount_returned - expected_return
                    shortage = -variance if variance < 0 else Decimal('0.00')
                    overage = variance if variance > 0 else Decimal('0.00')
                    
                    # Update the closing balance in transactions
                    for transaction in cash_transactions:
                        if transaction['type'] == 'closing_balance':
                            transaction['amount'] = closing_amount
                            break
                    else:
                        # Add new closing balance transaction
                        cash_transactions.append({
                            'time': timezone.now(),
                            'type': 'closing_balance',
                            'description': 'Closing Balance',
                            'amount': closing_amount,
                            'staff': request.user,
                            'notes': 'Closing balance from cash reconciliation',
                            'is_float': True
                        })
                    
                    messages.success(request, f'Closing balance saved: ₱{closing_amount:.2f}')
                
        except (ValueError, TypeError, InvalidOperation) as e:
            messages.error(request, f'Invalid amount: {str(e)}')
    
    context = {
        'today': today,
        'starting_cash': starting_cash,
        'change_used': change_used,
        'cash_sales': cash_sales,
        'amount_returned': amount_returned,
        'expected_return': expected_return,
        'variance': variance,
        'shortage': shortage,
        'overage': overage,
        'manual_override': manual_override,
        'cash_floats': cash_floats,
        'cash_orders': cash_orders,
        'cash_orders_count': cash_orders.count(),
        'cash_transactions': cash_transactions,
        'total_cash_received': total_cash_received,
        'total_change_given': total_change_given,
        'has_opening_float': bool(opening_float),
        'has_closing_balance': bool(closing_balance),
    }
    
    return render(request, 'reports/cash_reconciliation.html', context)

@login_required
@staff_required
def delete_adjustment(request, adjustment_id):
    """Delete a cash adjustment and refresh the page"""
    try:
        adjustment = get_object_or_404(CashFloat, id=adjustment_id, float_type='adjustment')
        
        if request.method == 'POST':
            adjustment_date = adjustment.date
            adjustment.delete()
            messages.success(request, 'Adjustment deleted successfully.')
            return redirect(f'{reverse("cash_reconciliation_report")}?date={adjustment_date}')
    except Exception as e:
        messages.error(request, f'Error deleting adjustment: {e}')
    
    return redirect('cash_reconciliation_report')

# ==================== DASHBOARD VIEWS ====================
@login_required
@staff_required
def dashboard(request):
    """Main dashboard - redirects to appropriate dashboard based on role"""
    if is_admin_user(request.user):
        return redirect('admin_dashboard')
    else:
        return redirect('staff_dashboard')

@login_required
@admin_required
def admin_dashboard(request):
    """Admin-only dashboard with business overview and enhanced completed orders tracking"""
    today = timezone.now().date()
    
    try:
        # Today's orders with completion tracking
        todays_orders = Order.objects.filter(created_at__date=today)
        completed_orders_today = todays_orders.filter(status='completed')
        
        # Order statistics with completion focus
        total_orders_today = todays_orders.count()
        completed_orders_count = completed_orders_today.count()
        kiosk_orders_today = todays_orders.filter(order_type='kiosk').count()
        staff_orders_today = todays_orders.filter(order_type='staff').count()
        pending_orders_today = todays_orders.filter(status='pending').count()
        
        # Revenue statistics - ONLY from completed orders
        total_revenue_today = completed_orders_today.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        kiosk_revenue_today = completed_orders_today.filter(order_type='kiosk').aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        staff_revenue_today = completed_orders_today.filter(order_type='staff').aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')

        # Payment method breakdown for today
        cash_transactions_today = completed_orders_today.filter(payment_method='cash').count()
        gcash_transactions_today = completed_orders_today.filter(payment_method='gcash').count()
        
        # COMPLETION RATE CALCULATIONS - NEW
        completion_rate_today = (completed_orders_count / total_orders_today * 100) if total_orders_today > 0 else 0
        
        # Daily sales for the last 7 days (for chart)
        daily_sales_labels = []
        daily_sales_values = []
        for offset in range(6, -1, -1):  # 7 days, oldest to newest
            day = today - timedelta(days=offset)
            label = day.strftime('%b %d')
            daily_total = Order.objects.filter(
                created_at__date=day,
                status='completed'
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            daily_sales_labels.append(label)
            daily_sales_values.append(float(daily_total))

        # Payment breakdown for chart (today, completed orders)
        payment_breakdown_qs = completed_orders_today.values('payment_method').annotate(
            total=Sum('total_amount')
        )
        payment_labels = []
        payment_values = []
        for row in payment_breakdown_qs:
            method = row['payment_method']
            label = 'Cash' if method == 'cash' else 'GCash' if method == 'gcash' else method.title()
            payment_labels.append(label)
            payment_values.append(float(row['total'] or 0))
        
        # COOKIE AND STOCK STATISTICS
        total_cookies = Cookie.objects.count()
        total_cookie_types = Cookie.objects.values('name').distinct().count()
        active_cookies = Cookie.objects.filter(is_available=True).count()
        low_stock_cookies = Cookie.objects.filter(stock_quantity__lt=10, stock_quantity__gt=0)
        out_of_stock_cookies = Cookie.objects.filter(stock_quantity=0)
        low_stock_count = low_stock_cookies.count()
        out_of_stock_count = out_of_stock_cookies.count()
        
        # Calculate active items percentage
        active_items_percentage = (active_cookies / total_cookies * 100) if total_cookies > 0 else 0
        
        # STAFF STATISTICS
        pending_staff = Staff.objects.filter(role='pending', is_active=False)
        pending_staff_count = pending_staff.count()
        total_staff = Staff.objects.filter(is_active=True).count()
        
        # Best selling cookie (from completed orders only)
        thirty_days_ago = today - timedelta(days=30)
        best_selling = OrderItem.objects.filter(
            order__status='completed',
            order__completed_at__date__gte=thirty_days_ago
        ).values('cookie__name').annotate(
            total_sold=Sum('quantity')
        ).order_by('-total_sold').first()
        
        best_selling_cookie = best_selling['cookie__name'] if best_selling else 'N/A'
        best_selling_count = best_selling['total_sold'] if best_selling else 0
        
        # Staff performance (based on completed orders)
        staff_performance = Staff.objects.filter(
            is_active=True,
            role__in=['staff', 'admin']
        ).annotate(
            total_completed_sales=Count('user__recorded_orders', 
                                      filter=Q(user__recorded_orders__status='completed')),
            total_completed_revenue=Sum('user__recorded_orders__total_amount', 
                                      filter=Q(user__recorded_orders__status='completed'))
        ).order_by('-total_completed_revenue')[:3]
        
        # Recent completed orders and latest orders (for tables)
        recent_completed_orders = Order.objects.filter(
            status='completed'
        ).select_related('customer', 'staff').order_by('-completed_at')[:10]

        latest_orders = todays_orders.select_related('customer', 'staff').order_by('-created_at')[:10]

        # Pending GCash verifications (for notifications/approvals)
        pending_gcash_orders = Order.objects.filter(payment_method='gcash', is_paid=False)
        pending_gcash_count = pending_gcash_orders.count()

        # Notifications for admin
        admin_notifications = []
        if low_stock_count:
            admin_notifications.append({
                'icon': 'fas fa-boxes',
                'title': 'Low stock warning',
                'message': f'{low_stock_count} item(s) are low on stock.'
            })
        if pending_gcash_count:
            admin_notifications.append({
                'icon': 'fas fa-mobile-alt',
                'title': 'Pending GCash verifications',
                'message': f'{pending_gcash_count} order(s) need manual verification.'
            })

        # Recent system activity logs
        recent_activity_logs = ActivityLog.objects.select_related('user', 'staff').order_by('-timestamp')[:8]
        
        context = {
            'today': today,
            'total_orders_today': total_orders_today,
            'completed_orders_count': completed_orders_count,
            'completion_rate_today': round(completion_rate_today, 1),
            'kiosk_orders_today': kiosk_orders_today,
            'staff_orders_today': staff_orders_today,
            'pending_orders_today': pending_orders_today,
            'total_revenue_today': total_revenue_today,
            'kiosk_revenue_today': kiosk_revenue_today,
            'staff_revenue_today': staff_revenue_today,
            'cash_transactions_today': cash_transactions_today,
            'gcash_transactions_today': gcash_transactions_today,
            'daily_sales_labels': daily_sales_labels,
            'daily_sales_values': daily_sales_values,
            'payment_labels': payment_labels,
            'payment_values': payment_values,
            'low_stock_cookies': low_stock_cookies,
            'out_of_stock_cookies': out_of_stock_cookies,
            
            # Existing statistics
            'total_cookies': total_cookies,
            'total_cookie_types': total_cookie_types,
            'active_cookies': active_cookies,
            'active_items_percentage': round(active_items_percentage, 1),
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'pending_staff': pending_staff,
            'pending_staff_count': pending_staff_count,
            'total_staff': total_staff,
            'best_selling_cookie': best_selling_cookie,
            'best_selling_count': best_selling_count,
            'staff_performance': staff_performance,
            'recent_completed_orders': recent_completed_orders,
            'latest_orders': latest_orders,
            'pending_gcash_orders': pending_gcash_orders,
            'pending_gcash_count': pending_gcash_count,
            'admin_notifications': admin_notifications,
            'recent_activity_logs': recent_activity_logs,
        }
        
    except Exception as e:
        messages.error(request, f'Error loading dashboard: {str(e)}')
        context = {
            'today': today,
            'total_orders_today': 0,
            'completed_orders_count': 0,
            'completion_rate_today': 0,
            'kiosk_orders_today': 0,
            'staff_orders_today': 0,
            'pending_orders_today': 0,
            'total_revenue_today': Decimal('0.00'),
            'kiosk_revenue_today': Decimal('0.00'),
            'staff_revenue_today': Decimal('0.00'),
            'hourly_completions': [],
            'low_stock_cookies': [],
            'out_of_stock_cookies': [],
            'total_cookies': 0,
            'total_cookie_types': 0,
            'active_cookies': 0,
            'active_items_percentage': 0,
            'low_stock_count': 0,
            'out_of_stock_count': 0,
            'pending_staff': [],
            'pending_staff_count': 0,
            'total_staff': 0,
            'best_selling_cookie': 'N/A',
            'best_selling_count': 0,
            'staff_performance': [],
            'recent_completed_orders': [],
        }
    
    return render(request, 'admin_dashboard.html', context)

@login_required
@staff_required
def staff_dashboard(request):
    """Staff dashboard with personal performance and completed orders tracking"""
    today = timezone.now().date()
    staff = request.user
    
    try:
        # Staff-specific statistics
        staff_orders_today = Order.objects.filter(
            staff=staff,
            created_at__date=today
        )
        
        # COMPLETED ORDERS TRACKING - NEW
        completed_orders_today = staff_orders_today.filter(status='completed')
        pending_orders_today = staff_orders_today.filter(status='pending')
        
        total_sales_today = completed_orders_today.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        orders_count_today = staff_orders_today.count()
        completed_count_today = completed_orders_today.count()
        pending_orders_count = pending_orders_today.count()
        
        # Recent completed orders by this staff
        recent_completed_orders = Order.objects.filter(
            staff=staff, 
            status='completed'
        ).select_related('customer').order_by('-completed_at')[:5]
        
        # Monthly performance for completed orders
        month_start = today.replace(day=1)
        monthly_completed = Order.objects.filter(
            staff=staff,
            status='completed',
            completed_at__date__gte=month_start
        )
        monthly_sales = monthly_completed.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        monthly_orders = monthly_completed.count()
        
        # Low stock and pending GCash metrics
        low_stock_threshold = 5
        low_stock_count = Cookie.objects.filter(stock_quantity__lte=low_stock_threshold, is_available=True).count()
        pending_gcash_count = Order.objects.filter(payment_method='gcash', is_paid=False, created_at__date=today).count()

        # Notifications (simple aggregation)
        notifications = []
        if low_stock_count:
            notifications.append({
                'type': 'warning',
                'icon': 'fas fa-boxes',
                'title': 'Low stock alert',
                'message': f'{low_stock_count} item(s) are low on stock.'
            })
        if pending_gcash_count:
            notifications.append({
                'type': 'info',
                'icon': 'fas fa-mobile-alt',
                'title': 'Pending GCash verification',
                'message': f'{pending_gcash_count} order(s) need GCash verification.'
            })

        # Recent activity logs for this staff
        recent_activity = ActivityLog.objects.filter(user=staff).order_by('-timestamp')[:5]
        
        # Order History (completed, cancelled, voided orders)
        order_history = Order.objects.filter(
            status__in=['completed', 'cancelled', 'voided']
        ).select_related('customer').prefetch_related('items__cookie').order_by('-created_at')[:20]
        
        # Orders per hour calculation removed - no longer needed
        
        # Top selling cookies today (all staff)
        try:
            top_cookies = OrderItem.objects.filter(
                order__status='completed',
                order__completed_at__date=today
            ).values(
                'cookie__name', 'cookie__price'
            ).annotate(
                quantity_sold=Sum('quantity'),
                total_revenue=Sum(F('quantity') * F('cookie__price'))
            ).order_by('-quantity_sold')[:5]
        except Exception as e:
            print(f"Error calculating top cookies: {e}")
            top_cookies = []

        latest_orders = Order.objects.select_related('customer', 'staff').prefetch_related('items').order_by('-created_at')[:10]

        context = {
            'today': today,
            'total_sales_today': total_sales_today,
            'orders_count_today': orders_count_today,
            'completed_count_today': completed_count_today,
            'pending_orders_count': pending_orders_count,
            'recent_staff_orders': staff_orders_today.order_by('-created_at')[:10],
            'latest_orders': latest_orders,
            'recent_completed_orders': recent_completed_orders,
            'monthly_sales': monthly_sales,
            'monthly_orders': monthly_orders,
            'staff': staff,
            'low_stock_count': low_stock_count,
            'pending_gcash_count': pending_gcash_count,
            'notifications': notifications,
            'recent_activity': recent_activity,
            'top_cookies': top_cookies,
            'order_history': order_history,
        }
        
    except Exception as e:
        messages.error(request, f'Error loading dashboard: {str(e)}')
        context = {
            'today': today,
            'total_sales_today': Decimal('0.00'),
            'orders_count_today': 0,
            'completed_count_today': 0,
            'pending_orders_count': 0,
            'recent_staff_orders': [],
            'latest_orders': [],
            'recent_completed_orders': [],
            'monthly_sales': Decimal('0.00'),
            'monthly_orders': 0,
            'staff': staff,
            'low_stock_count': 0,
            'pending_gcash_count': 0,
            'notifications': [],
            'recent_activity': [],
            'top_cookies': [],
            'order_history': [],
        }
    
    return render(request, 'staff_dashboard.html', context)

@login_required
@staff_required
def staff_profile(request):
    """Staff profile & security: show Staff ID, basic info, allow password change, and logout link"""
    staff_user = request.user
    staff_obj = getattr(staff_user, 'staff', None)

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')
        if form_type == 'profile':
            # Basic profile fields
            new_username = request.POST.get('username', '').strip()
            new_email = request.POST.get('email', '').strip()
            new_phone = request.POST.get('phone_number', '').strip()

            if new_username and new_username != staff_user.username:
                staff_user.username = new_username
            if new_email and new_email != staff_user.email:
                staff_user.email = new_email
            staff_user.save()

            if staff_obj is not None:
                if new_phone and new_phone != (staff_obj.phone_number or ''):
                    staff_obj.phone_number = new_phone
                    staff_obj.save()

            messages.success(request, 'Profile updated successfully!')
            return redirect('staff_profile')

        elif form_type == 'password':
            current_password = request.POST.get('current_password', '')
            new_password1 = request.POST.get('new_password1', '')
            new_password2 = request.POST.get('new_password2', '')

            if not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
                return redirect('staff_profile')
            if new_password1 != new_password2:
                messages.error(request, 'New passwords do not match.')
                return redirect('staff_profile')
            if new_password1 == current_password:
                messages.error(request, 'New password must be different from the current password.')
                return redirect('staff_profile')
            if len(new_password1) < 8:
                messages.error(request, 'New password must be at least 8 characters long.')
                return redirect('staff_profile')
            try:
                validate_password(new_password1, user=request.user)
            except ValidationError as e:
                messages.error(request, '; '.join(e.messages))
                return redirect('staff_profile')

            request.user.set_password(new_password1)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password updated successfully!')
            return redirect('staff_profile')

    context = {
        'staff_user': staff_user,
        'staff_obj': staff_obj,
    }
    return render(request, 'staff/profile.html', context)

# ==================== EXISTING CUSTOMER AUTHENTICATION (KEPT AS IS) ====================

@csrf_protect
def unified_login(request):
    """Unified login page for all user types with automatic role detection and Google OAuth"""
    print(f"UNIFIED LOGIN: User={request.user}, Authenticated={request.user.is_authenticated}")
    
    # If user is already authenticated, redirect to appropriate dashboard
    if request.user.is_authenticated and not request.user.is_anonymous:
        return redirect_user_by_role(request.user)
    
    # Handle POST requests for login
    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'login')
        print(f"POST request with form_type: {form_type}")
        
        if form_type == 'login':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            
            if not username or not password:
                messages.error(request, 'Please enter both username and password.')
                return redirect('home')
            
            print(f"Login attempt: {username}")
            
            # Handle Customer ID login (CUST format)
            user = None
            if username.upper().startswith('CUST'):
                try:
                    user_profile = UserProfile.objects.get(customer_id=username.upper(), user_type='customer')
                    user = user_profile.user
                    # Verify password for CUST ID login
                    if not user.check_password(password):
                        user = None
                        print("Password incorrect for CUST ID")
                    else:
                        print(f"CUST ID login successful: {username}")
                except UserProfile.DoesNotExist:
                    user = None
                    print(f"CUST ID not found: {username}")
            else:
                # Regular username/email login
                user = authenticate(request, username=username, password=password)
                print(f"Regular login result: {user}")
            
            if user is not None:
                auth_login(request, user)
                request.session.set_expiry(0)  # Session expires when browser closes
                
                # Log the activity
                log_activity(
                    user=user,
                    action='login',
                    description=f'User {username} logged in successfully via unified login',
                    ip_address=get_client_ip(request)
                )
                
                # Add success message here, before redirecting
                messages.success(request, f'Successfully signed in as {user.username}!')
                
                # Redirect based on user role
                return redirect_user_by_role(user, request)
            else:
                messages.error(request, 'Invalid username/password or Customer ID. Please try again.')
                return redirect('home')
        
        elif form_type == 'register':
            # Handle customer registration
            form = CustomerRegistrationForm(request.POST)
            if form.is_valid():
                try:
                    user = form.save()
                    log_activity(
                        user=user,
                        action='user_registered',
                        description=f'New customer registered: {user.profile.customer.name}',
                        ip_address=get_client_ip(request)
                    )
                    messages.success(request, f'Registration successful! Please log in with your username: {user.username}')
                    return redirect('home')
                except Exception as e:
                    messages.error(request, f'Registration failed: {str(e)}')
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
                        print(f"Validation error - {field}: {error}")
            
            return redirect('home')
    
    # Render the unified login page
    return render(request, 'unified_login.html', {
        'user': request.user
    })

def redirect_user_by_role(user, request=None):
    """Redirect user to appropriate dashboard based on their role.

    SAFETY: For Google/social logins and any user whose profile says
    'customer', ALWAYS send to customer_dashboard and NEVER to pending_approval.
    """
    print(f"Redirecting user by role: {user.username}")

    # NEW: Always send superusers to admin dashboard
    if getattr(user, "is_superuser", False):
        return redirect("admin_dashboard")
        
    # If user has a profile, obey it
    if hasattr(user, 'profile'):
        user_type = user.profile.user_type
        print(f"User type: {user_type}")

        # HARD RULE: If profile says customer, always go to customer dashboard
        if user_type == 'customer':
            print("Customer profile detected - prioritizing customer dashboard")
            return redirect('customer_dashboard')

        # Staff/admin only when explicitly marked as such
        if user_type in ['staff', 'admin']:
            from .decorators import is_approved_staff
            if is_approved_staff(user):
                print("Redirecting to staff/admin dashboard")
                return redirect('dashboard')
            else:
                # This is ONLY for real staff accounts, not Google customers
                print("User not approved, redirecting to pending approval")
                return redirect('pending_approval')

    # Fallback: no profile (shouldn't happen with Google, but be safe)
    print("No profile found, creating customer profile for authenticated user")
    from .models import UserProfile, Customer

    try:
        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={'user_type': 'customer'}
        )
        if user_profile.user_type != 'customer':
            user_profile.user_type = 'customer'
            user_profile.save()

        if not hasattr(user_profile, 'customer'):
            Customer.objects.get_or_create(
                user_profile=user_profile,
                defaults={
                    'name': user.get_full_name() or (user.email.split('@')[0] if user.email else user.username),
                    'email': user.email or ''
                }
            )
    except Exception as e:
        print(f"Error ensuring customer profile in redirect_user_by_role: {e}")

    # ALWAYS send this fallback case to customer dashboard
    return redirect('customer_dashboard')


@login_required
def login_complete(request):
    """Unified post-login redirect for all authentication methods.

    This view is used as the LOGIN_REDIRECT_URL / ACCOUNT_LOGIN_REDIRECT_URL
    so that both password logins and social logins (e.g., Google) are
    redirected through the same role-based routing logic.
    """
    print("LOGIN_COMPLETE: delegating to redirect_user_by_role")
    return redirect_user_by_role(request.user, request)

# Keep the old home view for backward compatibility, but redirect to unified login
def home(request):
    """Legacy home view - redirects to unified login"""
    return unified_login(request)

def public_home(request):
    """Public landing page with marketing content."""
    cookies_with_images = Cookie.objects.filter(
        is_available=True,
        stock_quantity__gt=0,
        image__isnull=False
    ).exclude(image='').order_by('-id')[:8]

    # Scan media folder for featured cookie images (e.g., media/cookies/* or media/*)
    featured_images = []
    try:
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        if media_root and os.path.isdir(media_root):
            patterns = [
                os.path.join(media_root, 'cookies', '*.*'),
                os.path.join(media_root, '*.*'),
            ]
            exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
            found = []
            for pattern in patterns:
                found.extend(glob.glob(pattern))
            # Filter by image extensions and unique order
            imgs = [p for p in found if os.path.splitext(p)[1].lower() in exts]
            # Make relative URLs
            for p in imgs:
                rel = p.replace(media_root, '').lstrip('\\/').replace('\\', '/')
                featured_images.append((media_url.rstrip('/') + '/' + rel))
            # De-duplicate and limit
            seen = set()
            dedup = []
            for url in featured_images:
                if url not in seen:
                    dedup.append(url)
                    seen.add(url)
            featured_images = dedup[:12]
    except Exception as _:
        featured_images = []

    return render(request, 'public_home.html', {
        'cookies_with_images': cookies_with_images,
        'featured_images': featured_images,
    })

def public_menu(request):
    """Public Menu page listing available cookies with optional search."""
    q = (request.GET.get('q') or '').strip()
    cookies = Cookie.objects.filter(is_available=True, stock_quantity__gt=0).select_related('category').order_by('name')
    if q:
        cookies = cookies.filter(models.Q(name__icontains=q) | models.Q(category__name__icontains=q))
    return render(request, 'public_menu.html', {
        'cookies': cookies,
        'q': q,
    })

    # Handle POST requests for login/registration (your existing code)
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        print(f"POST request with form_type: {form_type}")
        
        # Handle customer login from modal
        if form_type == 'customer_login':
            username = request.POST.get('username')
            password = request.POST.get('password')
            
            print(f"Customer login attempt: {username}")
            
            # Handle CUST ID login
            if username.upper().startswith('CUST'):
                try:
                    user_profile = UserProfile.objects.get(customer_id=username.upper(), user_type='customer')
                    user = user_profile.user
                    username = user.username
                except UserProfile.DoesNotExist:
                    user = None
            else:
                user = authenticate(request, username=username, password=password)
            
            if user and username.upper().startswith('CUST'):
                if not user.check_password(password):
                    user = None
            
            if user is not None and hasattr(user, 'profile') and user.profile.user_type == 'customer':
                auth_login(request, user)
                
                log_activity(
                    user=user,
                    action='login',
                    description=f'Customer {user.profile.customer.name} logged in',
                    ip_address=get_client_ip(request)
                )
                
                messages.success(request, f'Welcome back, {user.profile.customer.name}!')
                return redirect('customer_dashboard')
            else:
                messages.error(request, 'Invalid username/customer ID or password. Please try again.')
                
        # Handle staff login
        elif form_type == 'login':
            username = request.POST.get('username')
            password = request.POST.get('password')
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                auth_login(request, user)
                request.session.set_expiry(0)
                
                log_activity(
                    user=user,
                    action='login',
                    description=f'User {username} logged in successfully',
                    ip_address=get_client_ip(request)
                )
                
                # Check user type and redirect accordingly
                if hasattr(user, 'profile'):
                    user_type = user.profile.user_type
                    if user_type in ['staff', 'admin']:
                        if is_approved_staff(user):
                            messages.success(request, f'Welcome back, {username}!')
                            return redirect('dashboard')
                        else:
                            messages.info(request, 'Your account is pending admin approval.')
                            return redirect('pending_approval')
                    elif user_type == 'customer':
                        messages.success(request, f'Welcome back, {username}!')
                        return redirect('customer_dashboard')
                else:
                    # User has no profile, treat as customer
                    print("No profile found, creating customer profile for authenticated user")
                    UserProfile.objects.create(user=user, user_type='customer')
                    Customer.objects.create(
                        user_profile=user.profile,
                        name=user.get_full_name() or user.username,
                        email=user.email
                    )
                    messages.success(request, f'Welcome back, {username}!')
                    return redirect('customer_dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
    
    # Render the home page for unauthenticated users (GET request)
    print("Rendering home page for unauthenticated user")
    return render(request, 'home.html', {
        'user': request.user
    })

def pending_approval(request):
    """Show pending approval page for unapproved staff"""
    if not request.user.is_authenticated:
        return redirect('home')
    
    if hasattr(request.user, 'profile') and request.user.profile.user_type in ['staff', 'admin']:
        if is_approved_staff(request.user):
            return redirect('dashboard')
    
    return render(request, 'pending_approval.html')

def custom_logout(request):
    """Custom logout view"""
    if request.user.is_authenticated:
        log_activity(
            user=request.user,
            action='logout',
            description=f'User {request.user.username} logged out',
            ip_address=get_client_ip(request)
        )
    
    from django.contrib.auth import logout
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('public_home')

# ==================== EXISTING CUSTOMER AUTHENTICATION (KEPT AS IS) ====================

@csrf_protect
def customer_register(request):
    """Customer registration using the form class"""
    print("=== CUSTOMER REGISTRATION STARTED ===")
    
    # If user is already logged in as customer, redirect to dashboard
    if request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.user_type == 'customer':
        return redirect('customer_dashboard')
    
    if request.method == 'POST':
        print("=== POST REQUEST RECEIVED ===")
        print("POST data:", dict(request.POST))
        
        # Use the form for validation
        form = CustomerRegistrationForm(request.POST)
        
        if form.is_valid():
            try:
                print("=== FORM VALID - CREATING USER ===")
                # Save using the form's save method (which creates User, UserProfile, and Customer)
                user = form.save()
                
                print(f"✓ User created: {user.username} (ID: {user.id})")
                print(f"✓ UserProfile created with customer_id: {user.profile.customer_id}")
                print(f"✓ Customer record created: {user.profile.customer.name}")
                
                # Send verification email
                customer = user.profile.customer
                if send_verification_email(customer, request):
                    print("✓ Verification email sent")
                else:
                    print("⚠️ Failed to send verification email")
                
                # Log activity
                try:
                    log_activity(
                        user=user,
                        action='user_registered',
                        description=f'New customer registered: {user.profile.customer.name} with ID: {user.profile.customer_id}',
                        ip_address=get_client_ip(request)
                    )
                    print("✓ Activity logged")
                except Exception as log_error:
                    print(f"ℹ️ Activity logging failed: {log_error}")
                
                # Show message about email verification
                messages.success(request, f'Registration successful! Please check your email to verify your account.')
                
                # Redirect to login page with success parameter and username
                login_url = reverse('home')  # Changed from 'login' to 'home'
                # URL encode the username to handle special characters
                from urllib.parse import quote
                encoded_username = quote(user.username)
                success_url = f"{login_url}?registered=success&username={encoded_username}"
                return redirect(success_url)
                
            except Exception as e:
                error_message = f'Registration failed: {str(e)}'
                messages.error(request, error_message)
                print(f"ERROR: {error_message}")
                import traceback
                traceback.print_exc()
        else:
            # Form validation failed
            print("✗ Form validation failed")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
                    print(f"Validation error - {field}: {error}")
            
            return redirect('home')
    
    # If GET request, redirect to home (where registration modal is)
    return redirect('home')

def customer_login(request):
    """Customer login - accepts both username and customer ID"""
    if request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.user_type == 'customer':
        return redirect('customer_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            if username.upper().startswith('CUST'):
                try:
                    user_profile = UserProfile.objects.get(customer_id=username.upper(), user_type='customer')
                    user = user_profile.user
                    username = user.username
                except UserProfile.DoesNotExist:
                    user = None
            else:
                user = authenticate(request, username=username, password=password)
            
            if user and username.upper().startswith('CUST'):
                if not user.check_password(password):
                    user = None
            
            if user is not None and hasattr(user, 'profile') and user.profile.user_type == 'customer':
                auth_login(request, user)
                
                log_activity(
                    user=user,
                    action='login',
                    description=f'Customer {user.profile.customer.name} logged in',
                    ip_address=get_client_ip(request)
                )
                
                messages.success(request, f'Welcome back, {user.profile.customer.name}!')
                return redirect('customer_dashboard')
            else:
                messages.error(request, 'Invalid username/customer ID or password. Please try again.')
                
        except Exception as e:
            messages.error(request, 'Invalid username/customer ID or password. Please try again.')
    
    return redirect('customer_login')

# ==================== EXISTING CUSTOMER DASHBOARD (KEPT AS IS) ====================
@login_required
@customer_required
def customer_dashboard(request):
    """Customer dashboard"""
    # Immediately handle any POST requests by redirecting
    if request.method == 'POST':
        return redirect('customer_dashboard')
    
    # Your existing GET handling code
    customer = request.user.profile.customer

    # Recent orders (last 5)
    recent_orders = Order.objects.filter(customer=customer).order_by('-created_at')[:5]

    # Overall stats
    total_orders = Order.objects.filter(customer=customer).count()
    total_spent = Order.objects.filter(
        customer=customer,
        status='completed'
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    # Active order (any non-completed / non-cancelled order)
    active_order = (
        Order.objects
        .filter(customer=customer)
        .exclude(status__in=['completed', 'cancelled'])
        .order_by('-created_at')
        .first()
    )

    context = {
        'customer': customer,
        'recent_orders': recent_orders,
        'total_orders': total_orders,
        'total_spent': total_spent,
        'active_order': active_order,
    }
    return render(request, 'customer/dashboard.html', context)
@login_required
@customer_required
def customer_profile(request):
    """Customer profile"""
    customer = request.user.profile.customer
    total_orders = Order.objects.filter(customer=customer).count()
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')
        if form_type == 'profile':
            # Update profile fields
            customer.name = request.POST.get('name')
            customer.email = request.POST.get('email')
            customer.phone = request.POST.get('phone')
            customer.save()

            # Optionally update username and email on auth user
            new_username = request.POST.get('username', '').strip()
            if new_username and new_username != request.user.username:
                request.user.username = new_username
            if customer.email and customer.email != request.user.email:
                request.user.email = customer.email
            request.user.save()

            messages.success(request, 'Profile updated successfully!')
            return redirect('customer_profile')
        elif form_type == 'password':
            current_password = request.POST.get('current_password', '')
            new_password1 = request.POST.get('new_password1', '')
            new_password2 = request.POST.get('new_password2', '')

            if not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
                return redirect('customer_profile')
            if new_password1 != new_password2:
                messages.error(request, 'New passwords do not match.')
                return redirect('customer_profile')
            if new_password1 == current_password:
                messages.error(request, 'New password must be different from the current password.')
                return redirect('customer_profile')
            if len(new_password1) < 8:
                messages.error(request, 'New password must be at least 8 characters long.')
                return redirect('customer_profile')
            try:
                validate_password(new_password1, user=request.user)
            except ValidationError as e:
                messages.error(request, '; '.join(e.messages))
                return redirect('customer_profile')

            request.user.set_password(new_password1)
            request.user.save()
            # Keep user logged in after password change
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password updated successfully!')
            return redirect('customer_profile')

    context = {
        'customer': customer,
        'total_orders': total_orders,
    }
    return render(request, 'customer/profile.html', context)

@login_required
@customer_required
@require_POST
def delete_customer_account(request):
    """Delete customer account - requires confirmation"""
    try:
        user = request.user
        customer = user.profile.customer
        customer_name = customer.name
        customer_id = user.profile.customer_id
        
        # Log the account deletion
        log_activity(
            user=user,
            action='account_deleted',
            description=f'Customer account deleted: {customer_name} ({customer_id})',
            ip_address=get_client_ip(request)
        )
        
        # Delete related data (orders, etc.)
        Order.objects.filter(customer=customer).delete()
        
        # Delete customer profile
        customer.delete()
        
        # Delete user profile
        user.profile.delete()
        
        # Delete user account
        user.delete()
        
        # Log out the user
        logout(request)
        
        messages.success(request, 'Your account has been permanently deleted. All your data has been removed.')
        return redirect('public_home')
        
    except Exception as e:
        logger.error(f"Error deleting customer account: {str(e)}")
        messages.error(request, 'An error occurred while deleting your account. Please try again.')
        return redirect('customer_profile')

@login_required
@customer_required
def customer_google_reauth(request):
    """Initiate Google re-authentication with prompt=login and return to completion callback."""
    try:
        complete_url = request.build_absolute_uri(reverse('customer_reauth_complete'))
        try:
            provider_login_url = reverse('socialaccount_login', kwargs={'provider': 'google'})
        except Exception:
            # Fallback path used by django-allauth if reversing fails
            provider_login_url = '/accounts/google/login/'
        redirect_url = f"{provider_login_url}?process=login&prompt=login&next={quote(complete_url)}"
        return redirect(redirect_url)
    except Exception:
        messages.error(request, 'Unable to start re-authentication. Please try again later.')
        return redirect('customer_profile')

@login_required
@customer_required
def customer_reauth_complete(request):
    """Mark session as recently re-authenticated and return to profile."""
    request.session['reauth_ok'] = True
    request.session['reauth_ts'] = timezone.now().isoformat()
    messages.success(request, 'Re-authentication successful. You may proceed to delete your account.')
    return redirect('customer_profile')

@login_required
@customer_required
def order_history(request):
    """Customer order history with payment method display"""
    customer = request.user.profile.customer
    orders = Order.objects.filter(customer=customer).order_by('-created_at')
    
    # Calculate total spent
    total_spent = Order.objects.filter(
        customer=customer, 
        status='completed'
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    context = {
        'orders': orders,
        'customer': customer,
        'total_spent': total_spent,
    }
    return render(request, 'customer/order_history.html', context)


@login_required
@customer_required
@require_POST
def customer_cancel_order(request, order_id: int):
    """Allow a customer to cancel their own pending/unpaid order.

    Only orders belonging to the logged-in customer and currently in 'pending'
    status and not marked as paid can be cancelled.
    """
    customer = request.user.profile.customer

    try:
        order = get_object_or_404(Order, id=order_id, customer=customer)

        if order.status != 'pending' or order.is_paid:
            messages.error(request, 'This order can no longer be cancelled.')
            return redirect('order_history')

        order.status = 'cancelled'
        order.save()

        log_activity(
            user=request.user,
            action='order_cancelled',
            description=f'Customer cancelled order {order.order_id}',
            ip_address=get_client_ip(request),
            affected_model='Order',
            affected_id=order.id,
        )

        messages.success(request, f'Order {order.order_id} has been cancelled.')
    except Exception as e:
        messages.error(request, f'Unable to cancel order: {str(e)}')

    return redirect('order_history')

def _normalize_session_cart(request):
    """Ensure the session cart is a dict[str, int] with non-negative quantities."""
    raw_cart = request.session.get('cart', {}) or {}
    if not isinstance(raw_cart, dict):
        raw_cart = {}

    cleaned_cart = {}
    for key, value in raw_cart.items():
        try:
            cookie_id = str(int(key))
            quantity = int(value)
        except (TypeError, ValueError):
            continue

        if quantity > 0:
            cleaned_cart[cookie_id] = quantity

    if cleaned_cart != raw_cart:
        request.session['cart'] = cleaned_cart
        request.session.modified = True

    return cleaned_cart


def _get_session_cart_items(request):
    """Return detailed cart items and total amount from the session cart."""
    cart = _normalize_session_cart(request)
    items = []
    total = Decimal('0.00')

    if cart:
        cookies = Cookie.objects.filter(id__in=cart.keys()).select_related('category')
        valid_ids = set()

        for cookie in cookies:
            key = str(cookie.id)
            quantity = max(1, int(cart.get(key, 0)))
            subtotal = cookie.price * quantity

            total += subtotal
            items.append({
                'id': key,
                'cookie': cookie,
                'quantity': quantity,
                'subtotal': subtotal,
            })
            valid_ids.add(key)

        # Remove any cookies that no longer exist
        removed = False
        for cookie_id in list(cart.keys()):
            if cookie_id not in valid_ids or cart[cookie_id] <= 0:
                cart.pop(cookie_id, None)
                removed = True

        if removed:
            request.session['cart'] = cart
            request.session.modified = True

    return items, total, cart


@login_required
@customer_required
def customer_cart(request):
    """Customer cart page"""
    customer = request.user.profile.customer
    cart_items, cart_total, _ = _get_session_cart_items(request)

    context = {
        'customer': customer,
        'cart_items': cart_items,
        'cart_total': cart_total,
    }
    return render(request, 'customer/cart.html', context)


@login_required
@customer_required
@require_http_methods(["GET"])
def cart_state(request):
    """Return the current session cart state for the logged-in customer."""
    items, total, cart_map = _get_session_cart_items(request)

    serialized_items = []
    for entry in items:
        cookie = entry['cookie']
        serialized_items.append({
            'id': entry['id'],
            'name': cookie.name,
            'price': str(cookie.price),
            'quantity': entry['quantity'],
            'subtotal': str(entry['subtotal']),
            'image': cookie.image.url if getattr(cookie, 'image', None) else None,
            'stock': cookie.stock_quantity,
        })

    return JsonResponse({
        'success': True,
        'cart': cart_map,
        'items': serialized_items,
        'total_amount': str(total),
        'count': sum(cart_map.values()) if cart_map else 0,
    })


@login_required
@customer_required
@require_POST
def update_cart_item(request):
    """AJAX endpoint to add/update/remove a cookie in the customer's cart."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid request data.'}, status=400)

    cookie_id = payload.get('cookie_id')
    try:
        cookie_id = str(int(cookie_id))
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid cookie ID.'}, status=400)

    quantity = payload.get('quantity', 0)
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 0

    try:
        cookie = Cookie.objects.get(id=int(cookie_id), is_available=True)
    except Cookie.DoesNotExist:
        cart = _normalize_session_cart(request)
        cart.pop(cookie_id, None)
        request.session['cart'] = cart
        request.session.modified = True
        return JsonResponse({'success': False, 'error': 'Selected cookie is unavailable.'}, status=404)

    cart = _normalize_session_cart(request)

    if quantity <= 0:
        cart.pop(cookie_id, None)
    else:
        if quantity > cookie.stock_quantity:
            return JsonResponse({
                'success': False,
                'error': f'Only {cookie.stock_quantity} item(s) available for {cookie.name}.',
            }, status=400)
        cart[cookie_id] = quantity

    request.session['cart'] = cart
    request.session.modified = True

    items, total, cart_map = _get_session_cart_items(request)

    serialized_items = []
    for entry in items:
        cookie = entry['cookie']
        serialized_items.append({
            'id': entry['id'],
            'name': cookie.name,
            'price': str(cookie.price),
            'quantity': entry['quantity'],
            'subtotal': str(entry['subtotal']),
            'image': cookie.image.url if getattr(cookie, 'image', None) else None,
            'stock': cookie.stock_quantity,
        })

    return JsonResponse({
        'success': True,
        'cart': cart_map,
        'items': serialized_items,
        'total_amount': str(total),
        'count': sum(cart_map.values()),
    })


@login_required
@staff_required
@require_POST
def convert_cart_to_kiosk_order(request):
    """Create a kiosk order from the current session cart."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid request data.'}, status=400)

    customer_name = (payload.get('customer_name') or '').strip() or 'Kiosk Customer'
    customer_phone = (payload.get('customer_phone') or '').strip()
    notes = (payload.get('notes') or '').strip()
    payment_method = payload.get('payment_method') or 'cash'

    cart_items, total_amount, cart_map = _get_session_cart_items(request)

    if not cart_items:
        return JsonResponse({'success': False, 'error': 'Cart is empty.'}, status=400)

    order = Order.objects.create(
        customer_name=customer_name,
        customer_phone=customer_phone,
        staff=request.user,
        order_type='kiosk',
        total_amount=total_amount,
        payment_method=payment_method,
        status='pending',
        notes=notes,
    )

    for entry in cart_items:
        cookie = entry['cookie']
        OrderItem.objects.create(
            order=order,
            cookie=cookie,
            quantity=entry['quantity'],
            price=cookie.price
        )

    request.session['cart'] = {}
    request.session.modified = True

    log_activity(
        user=request.user,
        action='order_created',
        description=f'Kiosk order created from cart: {order.order_id} - ₱{total_amount:.2f}',
        ip_address=get_client_ip(request),
        affected_model='Order',
        affected_id=order.id
    )

    return JsonResponse({
        'success': True,
        'order': {
            'id': order.id,
            'order_id': order.order_id,
            'total_amount': str(order.total_amount),
            'payment_method': order.payment_method,
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
        }
    })

@login_required
@customer_required
def order_status(request):
    """Customer order status tracking"""
    customer = request.user.profile.customer
    # Get the most recent active order
    active_order = Order.objects.filter(
        customer=customer,
        status__in=['pending', 'preparing', 'ready']
    ).order_by('-created_at').first()
    
    context = {
        'customer': customer,
        'active_order': active_order,
    }
    return render(request, 'customer/order_status.html', context)

@login_required
@customer_required
def customer_notifications(request):
    """Customer notifications page"""
    customer = request.user.profile.customer

    # Build simple notifications derived from the customer's GCash orders
    notifications = []
    gcash_orders = (
        Order.objects.filter(customer=customer, payment_method='gcash')
        .order_by('-created_at')
    )

    for order in gcash_orders:
        # Approved payments
        if order.is_paid:
            notifications.append({
                'type': 'order',
                'title': 'GCash Payment Approved',
                'message': (
                    f'Payment Verified — Your order {order.display_id} is now being prepared. '
                    f'Total paid: ₱{order.total_amount}.'
                ),
                'created_at': order.gcash_verified_at or order.paid_at or order.updated_at,
            })
        # Rejected / cancelled before payment
        elif order.status in ['cancelled', 'voided']:
            notifications.append({
                'type': 'warning',
                'title': 'GCash Payment Issue',
                'message': f'Your GCash payment for order {order.display_id} was rejected or cancelled. You may place a new order and reupload a correct screenshot.',
                'created_at': order.updated_at,
            })

    context = {
        'customer': customer,
        'notifications': notifications,
    }
    return render(request, 'customer/notifications.html', context)

@login_required
@customer_required
def customer_help(request):
    """Customer help and support page"""
    customer = request.user.profile.customer
    context = {
        'customer': customer,
    }
    return render(request, 'customer/help.html', context)


@login_required
@admin_required
def admin_customer_list(request):
    """Admin view: list all customers with filters and basic stats"""
    customers = Customer.objects.select_related('user_profile__user').annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount', filter=Q(orders__status='completed')),
    )

    search = (request.GET.get('search') or '').strip()
    status_filter = (request.GET.get('status') or '').strip()
    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    if search:
        customers = customers.filter(
            Q(name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
            | Q(user_profile__customer_id__icontains=search)
            | Q(user_profile__user__username__icontains=search)
        )

    if status_filter == 'active':
        customers = customers.filter(user_profile__user__is_active=True)
    elif status_filter == 'inactive':
        customers = customers.filter(user_profile__user__is_active=False)

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            customers = customers.filter(date_joined__date__gte=start_date)
        except ValueError:
            start_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            customers = customers.filter(date_joined__date__lte=end_date)
        except ValueError:
            end_date = None

    customers = customers.order_by('-date_joined')

    context = {
        'customers': customers,
        'search': search,
        'status_filter': status_filter,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    return render(request, 'admin/customers_list.html', context)


@login_required
@admin_required
def admin_customer_orders(request, customer_id):
    """Admin view: order history for a specific customer"""
    customer = get_object_or_404(Customer.objects.select_related('user_profile__user'), id=customer_id)

    orders = customer.orders.all().order_by('-created_at')

    status_filter = (request.GET.get('status') or '').strip()
    payment_filter = (request.GET.get('payment') or '').strip()
    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    if status_filter:
        orders = orders.filter(status=status_filter)
    if payment_filter:
        orders = orders.filter(payment_method=payment_filter)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            orders = orders.filter(created_at__date__gte=start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            orders = orders.filter(created_at__date__lte=end_date)
        except ValueError:
            pass

    total_spent = orders.filter(status='completed').aggregate(total=Sum('total_amount'))['total'] or 0

    context = {
        'customer': customer,
        'orders': orders,
        'status_filter': status_filter,
        'payment_filter': payment_filter,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_spent': total_spent,
    }
    return render(request, 'admin/customer_orders.html', context)


@login_required
@admin_required
def admin_gcash_verifications(request):
    """Admin list of orders awaiting GCash verification"""
    qs = Order.objects.filter(payment_method='gcash', is_paid=False).select_related('staff', 'customer').order_by('-created_at')

    search = (request.GET.get('search') or '').strip()
    status_filter = (request.GET.get('status') or '').strip()
    date_str = (request.GET.get('date') or '').strip()

    if search:
        qs = qs.filter(
            Q(order_id__icontains=search)
            | Q(customer_name__icontains=search)
            | Q(gcash_reference__icontains=search)
            | Q(hex_id__icontains=search)
        )

    if status_filter:
        qs = qs.filter(status=status_filter)

    if date_str:
        try:
            day = datetime.strptime(date_str, '%Y-%m-%d').date()
            qs = qs.filter(created_at__date=day)
        except ValueError:
            pass

    pending_orders = qs

    context = {
        'pending_orders': pending_orders,
        'search': search,
        'status_filter': status_filter,
        'date': date_str,
    }
    return render(request, 'admin/gcash_verifications.html', context)


@login_required
@admin_required
def admin_store_settings(request):
    """Admin view to manage global store settings"""
    settings_obj = StoreSettings.get_solo()

    if request.method == 'POST':
        form = StoreSettingsForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Store settings have been updated.')
            return redirect('admin_store_settings')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StoreSettingsForm(instance=settings_obj)

    return render(request, 'admin/store_settings.html', {
        'form': form,
        'settings_obj': settings_obj,
    })


@login_required
@admin_required
@require_POST
def admin_activate_customer(request, customer_id):
    """Activate a customer's user account"""
    customer = get_object_or_404(Customer.objects.select_related('user_profile__user'), id=customer_id)
    user = customer.user_profile.user
    if not user.is_active:
        user.is_active = True
        user.save()
        messages.success(request, f"Customer {customer.name} has been activated.")
    else:
        messages.info(request, f"Customer {customer.name} is already active.")
    return redirect('admin_customer_list')


@login_required
@admin_required
@require_POST
def admin_deactivate_customer(request, customer_id):
    """Deactivate a customer's user account"""
    customer = get_object_or_404(Customer.objects.select_related('user_profile__user'), id=customer_id)
    user = customer.user_profile.user
    if user.is_active:
        user.is_active = False
        user.save()
        messages.warning(request, f"Customer {customer.name} has been deactivated.")
    else:
        messages.info(request, f"Customer {customer.name} is already inactive.")
    return redirect('admin_customer_list')


@login_required
@customer_required
def loyalty_rewards(request):
    """Loyalty rewards"""
    customer = request.user.profile.customer
    context = {
        'customer': customer,
    }
    return render(request, 'customer/loyalty_rewards.html', context)

# ==================== EXISTING INVENTORY MANAGEMENT (KEPT AS IS) ====================
@login_required
def inventory(request):
    search_query = request.GET.get('q', '')
    category_filter = request.GET.get('category', '')
    
    cookies = Cookie.objects.all().select_related('category')
    
    if category_filter:
        try:
            category_id = int(category_filter)
            cookies = cookies.filter(category_id=category_id)
        except (ValueError, TypeError):
            try:
                category = Category.objects.get(name__iexact=category_filter)
                cookies = cookies.filter(category=category)
                category_filter = str(category.id)
            except Category.DoesNotExist:
                category_filter = ''
    
    if search_query:
        cookies = cookies.filter(
            Q(name__icontains=search_query) |
            Q(flavor__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    today = timezone.now().date()
    next_week = today + timedelta(days=7)
    
    cookies_by_category = {}
    uncategorized_cookies = []
    
    for cookie in cookies:
        category = cookie.category
        if category:
            if category not in cookies_by_category:
                cookies_by_category[category] = []
            cookies_by_category[category].append(cookie)
        else:
            uncategorized_cookies.append(cookie)
    
    if uncategorized_cookies:
        class UncategorizedCategory:
            name = "Uncategorized"
            color = "#6c757d"
            icon = "fas fa-question-circle"
            pk = None
            
            def __str__(self):
                return self.name
        
        uncategorized_category = UncategorizedCategory()
        cookies_by_category[uncategorized_category] = uncategorized_cookies
    
    active_categories = Category.objects.filter(is_active=True)
    
    context = {
        'cookies_by_category': cookies_by_category,
        'category_choices': [(cat.id, cat.name) for cat in active_categories],
        'search_query': search_query,
        'category_filter': category_filter,
        'total_cookies': cookies.count(),
        'today': today,
        'next_week': next_week,
        'active_categories': active_categories,
    }
    
    return render(request, 'inventory.html', context)

@login_required
def add_cookie(request):
    if request.method == 'POST':
        form = CookieForm(request.POST)
        if form.is_valid():
            try:
                cookie = form.save()
                
                log_activity(
                    user=request.user,
                    action='cookie_added',
                    description=f'Added new cookie: {cookie.name}',
                    ip_address=get_client_ip(request),
                    affected_model='Cookie',
                    affected_id=cookie.id
                )
                
                return redirect('inventory')
            except Exception as e:
                form.add_error(None, f"Error saving cookie: {str(e)}")
    else:
        form = CookieForm()
    
    return render(request, 'cookie_form.html', {
        'form': form, 
        'title': 'Add New Cookie'
    })

@login_required
def update_cookie(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='Administrator').exists()):
        messages.error(request, 'You do not have permission to edit cookies.')
        return redirect('inventory')
    
    cookie = get_object_or_404(Cookie, pk=pk)
    
    if request.method == 'POST':
        form = CookieForm(request.POST, instance=cookie)
        if form.is_valid():
            form.save()
            
            log_activity(
                user=request.user,
                action='cookie_updated',
                description=f'Updated cookie: {cookie.name}',
                ip_address=get_client_ip(request),
                affected_model='Cookie',
                affected_id=cookie.id
            )
            
            messages.success(request, f'{cookie.name} has been updated successfully.')
            return redirect('inventory')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CookieForm(instance=cookie)
    
    return render(request, 'cookie_form.html', {
        'form': form, 
        'title': 'Update Cookie'
    })

@login_required
def delete_cookie(request, pk):
    cookie = get_object_or_404(Cookie, pk=pk)
    if request.method == 'POST':
        cookie_name = cookie.name
        cookie.delete()
        
        log_activity(
            user=request.user,
            action='cookie_deleted',
            description=f'Deleted cookie: {cookie_name}',
            ip_address=get_client_ip(request),
            affected_model='Cookie',
            affected_id=pk
        )
        
        return redirect('inventory')
    
    return render(request, 'cookie_confirm_delete.html', {'cookie': cookie})

# ==================== EXISTING CATEGORY MANAGEMENT (KEPT AS IS) ====================
@login_required
@admin_required
def category_list(request):
    """List all categories"""
    categories = Category.objects.all().order_by('name')
    
    for category in categories:
        category.cookie_count = category.get_cookie_count()
        category.active_cookies = category.cookies.filter(is_available=True).count()
    
    context = {
        'categories': categories,
    }
    return render(request, 'categories/category_list.html', context)

@login_required
@admin_required
def add_category(request):
    """Add a new category"""
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            
            log_activity(
                user=request.user,
                action='cookie_added',
                description=f'Added new category: {category.name}',
                ip_address=get_client_ip(request),
                affected_model='Category',
                affected_id=category.id
            )
            
            messages.success(request, f'Category "{category.name}" created successfully!')
            return redirect('category_list')
    else:
        form = CategoryForm()
    
    return render(request, 'categories/category_form.html', {
        'form': form,
        'title': 'Add New Category'
    })

@login_required
@admin_required
def update_category(request, pk):
    """Update an existing category"""
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            
            log_activity(
                user=request.user,
                action='cookie_updated',
                description=f'Updated category: {category.name}',
                ip_address=get_client_ip(request),
                affected_model='Category',
                affected_id=category.id
            )
            
            messages.success(request, f'Category "{category.name}" updated successfully!')
            return redirect('category_list')
    else:
        form = CategoryForm(instance=category)
    
    return render(request, 'categories/category_form.html', {
        'form': form,
        'title': 'Update Category'
    })

@login_required
@admin_required
def delete_category(request, pk):
    """Delete a category only if it has no cookies"""
    category = get_object_or_404(Category, pk=pk)
    
    if not category.can_delete():
        messages.error(
            request, 
            f'Cannot delete category "{category.name}" because it has {category.cookies.count()} cookies assigned. '
            'Please reassign or delete the cookies first.'
        )
        return redirect('category_list')
    
    if request.method == 'POST':
        try:
            category_name = category.name
            category.delete()
            
            log_activity(
                user=request.user,
                action='cookie_deleted',
                description=f'Deleted category: {category_name}',
                ip_address=get_client_ip(request),
                affected_model='Category',
                affected_id=pk
            )
            
            messages.success(request, f'Category "{category_name}" has been deleted successfully!')
            return redirect('category_list')
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('category_list')
        except Exception as e:
            messages.error(request, f'Error deleting category: {str(e)}')
            return redirect('category_list')
    
    context = {
        'category': category,
    }
    return render(request, 'categories/category_confirm_delete.html', context)

# ==================== EXISTING STAFF MANAGEMENT (KEPT AS IS) ====================
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from .models import Staff
from .utils import log_activity, get_client_ip

@ensure_csrf_cookie
@login_required
def staff_management(request):
    """Admin view to manage staff approvals"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to access staff management.')
        return redirect('dashboard')
    
    # Get pending staff (role='pending' OR is_active=False)
    pending_staff = Staff.objects.filter(
        role='pending'
    ).select_related('user').order_by('-user__date_joined')
    
    # Get active staff (excluding pending and superusers)
    active_staff = Staff.objects.filter(
        is_active=True
    ).exclude(role='pending').select_related('user').order_by('-date_joined')
    
    context = {
        'pending_staff': pending_staff,
        'active_staff': active_staff,
    }
    
    return render(request, 'staff_management.html', context)

@login_required
def approve_staff(request, staff_id):
    """Approve a staff member"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to approve staff.')
        return redirect('dashboard')
    
    try:
        staff = Staff.objects.get(id=staff_id)
        
        # Ensure we're only approving pending staff
        if staff.role != 'pending' and staff.is_active:
            messages.warning(request, f'Staff {staff.user.username} is already active.')
            return redirect('staff_management')
        
        staff.role = 'staff'  # Default role for approved staff
        staff.is_active = True
        staff.save()
        
        # Activate the associated user account
        staff.user.is_active = True
        staff.user.save()
        
        log_activity(
            user=request.user,
            action='staff_approved',
            description=f'Approved staff member: {staff.user.username} (ID: {staff.staff_id})',
            ip_address=get_client_ip(request),
            affected_model='Staff',
            affected_id=staff.id
        )
        
        messages.success(request, f'Staff {staff.user.username} has been approved successfully!')
    except Staff.DoesNotExist:
        messages.error(request, 'Staff member not found.')
    
    return redirect('staff_management')

@login_required
def reject_staff(request, staff_id):
    """Reject a staff member (delete their account)"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to reject staff.')
        return redirect('dashboard')
    
    try:
        staff = Staff.objects.get(id=staff_id)
        username = staff.user.username
        staff_id_value = staff.staff_id
        
        log_activity(
            user=request.user,
            action='staff_rejected',
            description=f'Rejected staff member: {username} (ID: {staff_id_value})',
            ip_address=get_client_ip(request),
            affected_model='Staff',
            affected_id=staff.id
        )
        
        # Delete the staff record and user
        staff.user.delete()
        # Staff record will be automatically deleted via CASCADE
        
        messages.success(request, f'Staff {username} has been rejected and removed from the system.')
    except Staff.DoesNotExist:
        messages.error(request, 'Staff member not found.')
    
    return redirect('staff_management')

@login_required
def edit_staff(request, staff_id):
    """Edit staff member details"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to edit staff.')
        return redirect('dashboard')
    
    staff = get_object_or_404(Staff, id=staff_id)
    
    if request.method == 'POST':
        # Handle staff editing logic here
        role = request.POST.get('role')
        if role in ['staff', 'manager', 'admin']:
            old_role = staff.get_role_display()
            staff.role = role
            staff.save()
            
            log_activity(
                user=request.user,
                action='staff_updated',
                description=f'Updated staff {staff.user.username} role from {old_role} to {staff.get_role_display()}',
                ip_address=get_client_ip(request),
                affected_model='Staff',
                affected_id=staff.id
            )
            
            messages.success(request, f'Staff {staff.user.username} has been updated successfully!')
        return redirect('staff_management')
    
    # For GET request, you might want to render an edit form
    # This is a simplified version - you might want to create a proper form
    context = {
        'staff': staff,
    }
    return render(request, 'edit_staff.html', context)

@login_required
def deactivate_staff(request, staff_id):
    """Deactivate a staff member"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to deactivate staff.')
        return redirect('dashboard')
    
    try:
        staff = Staff.objects.get(id=staff_id)
        
        # Prevent self-deactivation and superuser deactivation
        if staff.user == request.user:
            messages.error(request, 'You cannot deactivate your own account.')
            return redirect('staff_management')
        
        if staff.user.is_superuser:
            messages.error(request, 'Cannot deactivate superuser accounts.')
            return redirect('staff_management')
        
        staff.user.is_active = False
        staff.user.save()
        
        log_activity(
            user=request.user,
            action='staff_deactivated',
            description=f'Deactivated staff member: {staff.user.username}',
            ip_address=get_client_ip(request),
            affected_model='Staff',
            affected_id=staff.id
        )
        
        messages.success(request, f'Staff {staff.user.username} has been deactivated.')
    except Staff.DoesNotExist:
        messages.error(request, 'Staff member not found.')
    
    return redirect('staff_management')

@login_required
def activate_staff(request, staff_id):
    """Activate a staff member"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to activate staff.')
        return redirect('dashboard')
    
    try:
        staff = Staff.objects.get(id=staff_id)
        
        staff.user.is_active = True
        staff.user.save()
        
        log_activity(
            user=request.user,
            action='staff_activated',
            description=f'Activated staff member: {staff.user.username}',
            ip_address=get_client_ip(request),
            affected_model='Staff',
            affected_id=staff.id
        )
        
        messages.success(request, f'Staff {staff.user.username} has been activated.')
    except Staff.DoesNotExist:
        messages.error(request, 'Staff member not found.')
    
    return redirect('staff_management')

@login_required
def delete_staff(request, staff_id):
    """Permanently delete a staff member"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to delete staff.')
        return redirect('dashboard')
    
    try:
        staff = Staff.objects.get(id=staff_id)
        
        # Prevent self-deletion and superuser deletion
        if staff.user == request.user:
            messages.error(request, 'You cannot delete your own account.')
            return redirect('staff_management')
        
        if staff.user.is_superuser:
            messages.error(request, 'Cannot delete superuser accounts.')
            return redirect('staff_management')
        
        username = staff.user.username
        
        log_activity(
            user=request.user,
            action='staff_deleted',
            description=f'Deleted staff member: {username}',
            ip_address=get_client_ip(request),
            affected_model='Staff',
            affected_id=staff.id
        )
        
        staff.user.delete()
        
        messages.success(request, f'Staff {username} has been permanently deleted.')
    except Staff.DoesNotExist:
        messages.error(request, 'Staff member not found.')
    
    return redirect('staff_management')

# ==================== EXISTING ACTIVITY LOGS (KEPT AS IS) ====================
@login_required
@admin_required
def activity_logs(request):
    """Admin view showing all activity logs"""
    # Get filter parameters
    date_filter = request.GET.get('date', '')
    action_filter = request.GET.get('action', '')
    user_filter = request.GET.get('user', '')
    
    # Start with all activity logs
    activity_logs = ActivityLog.objects.all().select_related('user', 'staff').order_by('-timestamp')
    
    # Apply filters
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            activity_logs = activity_logs.filter(timestamp__date=filter_date)
        except ValueError:
            pass
    
    if action_filter:
        activity_logs = activity_logs.filter(action=action_filter)
    
    if user_filter:
        activity_logs = activity_logs.filter(
            Q(user__username__icontains=user_filter) |
            Q(staff__user__username__icontains=user_filter)
        )
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(activity_logs, 50)  # 50 logs per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get summary statistics
    today = timezone.now().date()
    today_logs = ActivityLog.objects.filter(timestamp__date=today)
    
    summary_stats = {
        'total_activities_today': today_logs.count(),
        'total_users_active_today': today_logs.values('user').distinct().count(),
        'sales_activities_today': today_logs.filter(action__in=['order_created', 'order_updated', 'order_completed', 'order_voided']).count(),
        'inventory_activities_today': today_logs.filter(action__in=['cookie_added', 'cookie_updated', 'cookie_deleted', 'inventory_updated']).count(),
    }
    
    # Get action types for filter dropdown
    action_choices = ActivityLog.ACTION_CHOICES
    
    context = {
        'page_obj': page_obj,
        'activity_logs': page_obj.object_list,
        'summary_stats': summary_stats,
        'action_choices': action_choices,
        'date_filter': date_filter,
        'action_filter': action_filter,
        'user_filter': user_filter,
    }
    
    return render(request, 'activity_logs.html', context)

# ==================== EXISTING VOID LOGS (KEPT AS IS) ====================
@login_required
@admin_required
def void_logs(request):
    """Admin view showing all voided sales with details"""
    # Get filter parameters
    date_filter = request.GET.get('date', '')
    staff_filter = request.GET.get('staff', '')
    
    # Start with all void logs
    void_logs = VoidLog.objects.all().select_related(
        'order', 'staff_member', 'admin_user', 'staff_member__user'
    ).order_by('-void_date')
    
    # Apply filters
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            void_logs = void_logs.filter(void_date__date=filter_date)
        except ValueError:
            pass
    
    if staff_filter:
        void_logs = void_logs.filter(staff_member_id=staff_filter)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(void_logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary statistics
    today = timezone.now().date()
    today_voids = VoidLog.objects.filter(void_date__date=today)
    
    summary_stats = {
        'total_voids_today': today_voids.count(),
        'total_voids': void_logs.count(),
        'total_voided_amount': sum([log.original_total for log in void_logs]),
    }
    
    # Get all staff for filter dropdown
    all_staff = Staff.objects.filter(is_active=True, role__in=['staff', 'admin'])
    
    context = {
        'page_obj': page_obj,
        'void_logs': page_obj.object_list,
        'summary_stats': summary_stats,
        'all_staff': all_staff,
        'date_filter': date_filter,
        'staff_filter': staff_filter,
    }
    
    return render(request, 'void_logs.html', context)

# ==================== EXISTING DAILY SALES REPORTING (KEPT AS IS) ====================
@login_required
@staff_required
def daily_sales_report(request):
    """Staff daily sales report submission"""
    today = timezone.now().date()
    
    try:
        # Get today's completed orders for this staff member
        # FIX: Use request.user (User instance) instead of request.user.staff (Staff instance)
        today_sales = Order.objects.filter(
            staff=request.user,  # Use User instance, not Staff instance
            status='completed',
            completed_at__date=today
        )
        
        # Check if staff has already submitted today's report
        # FIX: Use request.user (User instance) instead of request.user.staff (Staff instance)
        existing_report = Order.objects.filter(
            staff=request.user,  # Use User instance, not Staff instance
            is_daily_report=True,
            report_date=today
        ).exists()
        
        # Calculate today's sales summary
        total_sales_today = today_sales.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        # Get sales breakdown by cookie
        sales_summary = OrderItem.objects.filter(
            order__in=today_sales
        ).values(
            'cookie__name', 'cookie__price'
        ).annotate(
            total_quantity=Sum('quantity')
        ).order_by('-total_quantity')
        
        # Calculate total items sold today
        total_items_today = OrderItem.objects.filter(
            order__in=today_sales
        ).aggregate(
            total_items=Sum('quantity')
        )['total_items'] or 0
        
        if request.method == 'POST':
            # Check if already submitted
            if existing_report:
                messages.error(request, 'You have already submitted your daily sales report for today.')
                return redirect('daily_sales_report')
            
            # Validate there are sales to report
            if today_sales.count() == 0:
                messages.error(request, 'No sales recorded today. Cannot submit empty report.')
                return redirect('daily_sales_report')
            
            payment_method = request.POST.get('payment_method', 'cash')
            sales_date = request.POST.get('sales_date', today)
            
            try:
                # Create a daily report order
                daily_report = Order.objects.create(
                    staff=request.user,  # Use User instance
                    order_type='staff',
                    total_amount=total_sales_today,
                    payment_method=payment_method,
                    status='completed',
                    is_daily_report=True,
                    report_date=sales_date,
                    notes=f"Daily sales report submitted by {request.user.username}"
                )
                
                # Log the activity
                log_activity(
                    user=request.user,
                    action='daily_report_submitted',
                    description=f'Submitted daily sales report for {sales_date} - ₱{total_sales_today}',
                    ip_address=get_client_ip(request),
                    affected_model='Order',
                    affected_id=daily_report.id
                )
                
                messages.success(request, f'Daily sales report submitted successfully! Total sales: ₱{total_sales_today}')
                return redirect('dashboard')
                
            except Exception as e:
                messages.error(request, f'Error submitting report: {str(e)}')
        
        context = {
            'today': today,
            'today_sales': today_sales,
            'total_sales_today': total_sales_today,
            'sales_summary': sales_summary,
            'total_items_today': total_items_today,
            'has_submitted_today': existing_report,
        }
        
    except Exception as e:
        messages.error(request, f'Error loading daily sales report: {str(e)}')
        context = {
            'today': today,
            'today_sales': Order.objects.none(),
            'total_sales_today': Decimal('0.00'),
            'sales_summary': [],
            'total_items_today': 0,
            'has_submitted_today': False,
        }
    
    return render(request, 'daily_sales_report.html', context)
@login_required
@admin_required
def admin_sales_monitoring(request):
    """Admin view to monitor all staff sales reports with enhanced analytics - UPDATED for completed orders"""
    if not request.user.is_superuser and not (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'):
        messages.error(request, 'You do not have permission to access sales monitoring.')
        return redirect('dashboard')
    
    # Default to today's date
    selected_date = request.GET.get('date', timezone.now().date().isoformat())
    staff_filter = request.GET.get('staff', '')
    
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except:
        selected_date = timezone.now().date()
    
    # Get COMPLETED orders for the selected date
    completed_orders = Order.objects.filter(
        status='completed', 
        completed_at__date=selected_date
    )
    daily_reports = Order.objects.filter(is_daily_report=True, report_date=selected_date)
    
    # Apply staff filter if selected
    if staff_filter:
        # FIX: Convert staff_filter to User instance
        try:
            staff_obj = Staff.objects.get(id=staff_filter)
            completed_orders = completed_orders.filter(staff=staff_obj.user)
            daily_reports = daily_reports.filter(staff=staff_obj.user)
        except Staff.DoesNotExist:
            pass
    
    # Calculate daily summary from COMPLETED orders
    daily_summary = {
        'total_sales': completed_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
        'total_transactions': completed_orders.count(),
        'average_sale': completed_orders.aggregate(avg=Avg('total_amount'))['avg'] or 0,
        'daily_reports_count': daily_reports.count(),
        'staff_with_reports': daily_reports.values('staff').distinct().count(),
        'voided_sales': Order.objects.filter(status='voided', created_at__date=selected_date).count(),
        'completion_rate': (completed_orders.count() / Order.objects.filter(created_at__date=selected_date).count() * 100) if Order.objects.filter(created_at__date=selected_date).count() > 0 else 0,
    }
    
    # Sales by staff - Only show staff with completed sales - FIXED
    all_active_staff = Staff.objects.filter(is_active=True, role__in=['staff', 'admin']).select_related('user')
    staff_sales_data = []
    
    for staff in all_active_staff:
        # Get COMPLETED sales for this staff member on selected date
        # FIX: Use staff.user (User instance) instead of staff (Staff instance)
        staff_completed_orders = completed_orders.filter(staff=staff.user)
        staff_daily_reports = daily_reports.filter(staff=staff.user)
        
        total_sales = staff_completed_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        transaction_count = staff_completed_orders.count()
        daily_reports_count = staff_daily_reports.count()
        
        # Calculate average from completed orders
        avg_sales = total_sales / transaction_count if transaction_count > 0 else 0
        
        # Only include staff with completed sales activity OR daily reports
        if total_sales > 0 or daily_reports_count > 0:
            staff_sales_data.append({
                'staff_id': staff.id,
                'staff_name': staff.user.username,
                'staff_staff_id': staff.staff_id,
                'staff_sales': total_sales,
                'staff_transactions': transaction_count,
                'daily_reports': daily_reports_count,
                'avg_sales_per_transaction': avg_sales
            })
    
    # Sort by sales (highest first)
    staff_sales_data.sort(key=lambda x: x['staff_sales'], reverse=True)
    
    # Top selling items for the day from COMPLETED orders
    top_items = OrderItem.objects.filter(
        order__status='completed',
        order__completed_at__date=selected_date
    ).values('cookie__name').annotate(
        quantity_sold=Sum('quantity'),
        revenue=Sum('price')
    ).order_by('-quantity_sold')[:10]
    
    # Calculate average price for top items
    top_items_data = []
    for item in top_items:
        if item['quantity_sold'] > 0:
            avg_price = item['revenue'] / item['quantity_sold']
        else:
            avg_price = 0

        item_data = dict(item)
        item_data['avg_price'] = avg_price
        top_items_data.append(item_data)

    # Staff who haven't submitted daily reports
    staff_with_reports = daily_reports.values_list('staff_id', flat=True)
    staff_without_reports = all_active_staff.exclude(user_id__in=staff_with_reports)

    # NEW: Recent completed orders for monitoring
    recent_completed_orders = completed_orders.select_related('customer', 'staff').order_by('-completed_at')[:10]

    context = {
        'selected_date': selected_date,
        'staff_filter': staff_filter,
        'completed_orders': completed_orders,
        'daily_reports': daily_reports,
        'daily_summary': daily_summary,
        'sales_by_staff': staff_sales_data,
        'top_items': top_items_data,
        'staff_without_reports': staff_without_reports,
        'recent_completed_orders': recent_completed_orders,
        'all_staff': all_active_staff,
    }

    return render(request, 'admin_sales_monitoring.html', context)


@login_required
@admin_required
def admin_sales_monitoring_csv(request):
    selected_date = request.GET.get('date', timezone.now().date().isoformat())
    staff_filter = request.GET.get('staff', '')

    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except Exception:
        selected_date = timezone.now().date()

    completed_orders = Order.objects.filter(
        status='completed',
        completed_at__date=selected_date
    ).select_related('customer', 'staff')

    if staff_filter:
        try:
            staff_obj = Staff.objects.get(id=staff_filter)
            completed_orders = completed_orders.filter(staff=staff_obj.user)
        except Staff.DoesNotExist:
            completed_orders = completed_orders.none()

    response = HttpResponse(content_type='text/csv')
    filename = f"sales_{selected_date.isoformat()}"
    if staff_filter:
        filename += f"_staff_{staff_filter}"
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date',
        'Order ID',
        'Staff',
        'Customer',
        'Payment Method',
        'Order Type',
        'Total Amount',
        'Status',
    ])

    for order in completed_orders.order_by('completed_at'):
        writer.writerow([
            order.completed_at.strftime('%Y-%m-%d %H:%M') if order.completed_at else '',
            order.order_id,
            order.staff.username if order.staff else '',
            getattr(order, 'customer_name', '') or (order.customer.name if getattr(order, 'customer', None) else ''),
            order.payment_method,
            order.get_order_type_display() if hasattr(order, 'get_order_type_display') else order.order_type,
            f"{order.total_amount}",
            order.status,
        ])

    return response


@login_required
def staff_sales_history(request):
    """Staff can view their own sales history"""
    # Default to last 7 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=7)
    
    if request.method == 'POST':
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        payment_method = request.POST.get('payment_method', '').strip().lower()
        query = request.POST.get('q', '').strip()
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        payment_method = ''
        query = ''
    
    # Get sales made by this staff member (completed only)
    orders = Order.objects.filter(
        staff=request.user,
        status='completed',
        created_at__date__range=[start_date, end_date]
    )
    
    if payment_method:
        orders = orders.filter(payment_method=payment_method)
    
    if query:
        orders = orders.filter(
            Q(order_id__icontains=query) |
            Q(customer_name__icontains=query)
        )
    
    orders = orders.order_by('-created_at')
    
    # Calculate summary (orders already completed)
    completed_orders = orders
    summary = {
        'total_sales': completed_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
        'total_transactions': completed_orders.count(),
        'average_sale': completed_orders.aggregate(avg=Avg('total_amount'))['avg'] or 0,
        'voided_sales': 0,
    }
    
    context = {
        'sales': orders,  # Use 'sales' to match template
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
        'payment_method': payment_method,
        'query': query,
    }
    
    return render(request, 'staff_sales_history.html', context)

# ==================== EXISTING SEARCH AND API FUNCTIONS (KEPT AS IS) ====================
@login_required
def search_cookies(request):
    """AJAX endpoint for searching cookies"""
    query = request.GET.get('q', '').strip().lower()

    cookies = Cookie.objects.filter(stock_quantity__gt=0)

    if query:
        filtered_cookies = []
        for cookie in cookies:
            if (query in cookie.name.lower() or
                query in cookie.get_flavor_display().lower() or
                (cookie.description and query in cookie.description.lower())):
                filtered_cookies.append(cookie)
        cookies = filtered_cookies[:10]
    else:
        cookies = list(cookies[:10])

    results = []
    for cookie in cookies:
        results.append({
            'id': cookie.id,
            'name': cookie.name,
            'flavor': cookie.get_flavor_display(),
            'price': str(cookie.price),
            'stock': cookie.stock_quantity
        })

    return JsonResponse({'results': results})

@login_required
def search_customers(request):
    """API endpoint for customer search"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    customers = Customer.objects.filter(
        Q(name__icontains=query) |
        Q(user_profile__customer_id__icontains=query) |
        Q(phone__icontains=query)
    )[:10]
    
    results = []
    for customer in customers:
        results.append({
            'id': customer.id,
            'name': customer.name,
            'customer_id': customer.user_profile.customer_id if customer.user_profile else 'N/A',
            'phone': customer.phone or 'No phone',
            'email': customer.email or 'No email',
            'loyalty_points': customer.loyalty_points
        })
    
    return JsonResponse({'results': results})

# ==================== EXISTING ORDER COMPLETION FUNCTIONS (KEPT AS IS) ====================
@login_required
@admin_required
def complete_order_payment(request, order_id):
    """Mark a cash order as paid and complete the payment"""
    try:
        order = get_object_or_404(Order, id=order_id)
        
        # Verify it's a cash order with pending payment
        if order.payment_method != 'cash' or order.status != 'pending':
            return JsonResponse({
                'success': False, 
                'error': 'This order cannot be marked as paid.'
            })
        
        # Update order status
        order.status = 'completed'
        order.is_paid = True
        order.paid_at = timezone.now()
        order.save()
        
        # Add loyalty points to customer
        try:
            if order.customer:
                points_earned = int(order.total_amount)
                order.customer.loyalty_points += points_earned
                order.customer.save()
        except Customer.DoesNotExist:
            pass  # Customer might not exist in database (walk-in)
        
        # Log the payment completion
        log_activity(
            user=request.user,
            action='order_completed',
            description=f'Cash payment completed for order: {order.order_id} - ₱{order.total_amount:.2f}',
            ip_address=get_client_ip(request),
            affected_model='Order',
            affected_id=order.id
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Order {order.order_id} marked as paid successfully!',
            'order_id': order.order_id,
            'new_status': order.status,
            'status_display': order.get_status_display()
        })
        
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# ==================== EXISTING DEBUG AND TEST FUNCTIONS (KEPT AS IS) ====================
@login_required
def debug_user_status(request):
    """Debug view to check user permissions"""
    user_info = {
        'username': request.user.username,
        'is_superuser': request.user.is_superuser,
        'has_staff_profile': hasattr(request.user, 'staff'),
        'staff_role': getattr(request.user.staff, 'role', 'No staff profile') if hasattr(request.user, 'staff') else 'No staff profile',
        'is_admin': request.user.is_superuser or (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'),
    }
    
    # Staff statistics
    pending_count = Staff.objects.filter(role='pending', is_active=False).count()
    total_staff = Staff.objects.count()
    
    return JsonResponse({
        'user_info': user_info,
        'staff_stats': {
            'pending_count': pending_count,
            'total_staff': total_staff,
        }
    })

def debug_registration_test(request):
    """Test if registration creates Staff records"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        results = []
        
        try:
            # Step 1: Create user
            user = User.objects.create_user(username=username, email=email, password=password)
            results.append(f"✓ User created: {user.username}")
            
            # Step 2: Create customer
            customer = Customer.objects.create(user_profile=user.profile, name=username, email=email)
            results.append(f"✓ Customer created: {customer.name}")
            
            # Step 3: Create staff
            staff = Staff.objects.create(user=user, role='pending', is_active=False)
            results.append(f"✓ Staff created: {staff.staff_id} - Role: {staff.role}")
            
            # Step 4: Add to group
            staff_group, created = Group.objects.get_or_create(name='Staff')
            user.groups.add(staff_group)
            results.append(f"✓ Added to Staff group")
            
            return JsonResponse({'status': 'success', 'results': results})
            
        except Exception as e:
            # Clean up if anything fails
            if 'user' in locals():
                user.delete()
            return JsonResponse({'status': 'error', 'error': str(e), 'results': results})
    
    return render(request, 'debug_registration_test.html')

def debug_database_state(request):
    """See what's currently in the database"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Admin access required'})
    
    data = {
        'users': list(User.objects.values('id', 'username', 'email', 'is_active')),
        'customers': list(Customer.objects.values('id', 'user_profile_id', 'name', 'email')),
        'staff': list(Staff.objects.values('id', 'user_id', 'staff_id', 'role', 'is_active')),
        'groups': list(Group.objects.values('id', 'name'))
    }
    
    return JsonResponse(data)

def debug_all_staff(request):
    """Debug view to see all staff"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Admin access required'})
    
    staff_list = Staff.objects.all()
    staff_data = []
    for staff in staff_list:
        staff_data.append({
            'id': staff.id,
            'username': staff.user.username,
            'staff_id': staff.staff_id,
            'role': staff.role,
            'is_active': staff.is_active,
            'date_joined': staff.date_joined
        })
    
    return JsonResponse({'staff': staff_data})

def debug_csrf_issue(request):
    """Debug view to identify CSRF issues"""
    print("=== CSRF DEBUG INFO ===")
    print(f"Request method: {request.method}")
    print(f"Path: {request.path}")
    print(f"POST data: {dict(request.POST)}")
    print(f"GET data: {dict(request.GET)}")
    print(f"User: {request.user}")
    print(f"User authenticated: {request.user.is_authenticated}")
    print("=======================")
    
    return JsonResponse({
        'method': request.method,
        'path': request.path,
        'post_data': dict(request.POST),
        'user': str(request.user),
        'authenticated': request.user.is_authenticated
    })

def debug_form_data(request):
    """Debug view to see what form data is being received"""
    if request.method == 'POST':
        print("=== DEBUG FORM DATA ===")
        print("POST data:", dict(request.POST))
        print("Method:", request.method)
        print("User:", request.user)
        print("Path:", request.path)
        return JsonResponse({
            'status': 'received',
            'post_data': dict(request.POST),
            'message': 'Form data received successfully'
        })
    
    return JsonResponse({'status': 'ready', 'message': 'Send a POST request to test'})
@login_required
@staff_required
def debug_kiosk_orders(request):
    """Debug view to see what kiosk orders exist and their relationships"""
    print("=== DEBUG KIOSK ORDERS ===")
    
    from django.db import models
    
    # Check all kiosk orders
    all_kiosk_orders = Order.objects.filter(order_type='kiosk')
    print(f"Total kiosk orders: {all_kiosk_orders.count()}")
    
    # Get Order model field information
    order_fields = []
    for field in Order._meta.get_fields():
        order_fields.append({
            'name': field.name,
            'type': type(field).__name__,
            'related_model': field.related_model.__name__ if field.is_relation else None,
            'related_name': getattr(field, 'related_name', None)
        })
    
    print("=== ORDER MODEL FIELDS ===")
    for field_info in order_fields:
        print(f"Field: {field_info['name']} | Type: {field_info['type']} | Related: {field_info['related_model']} | Related Name: {field_info['related_name']}")
    
    # Check pending kiosk orders
    pending_kiosk_orders = Order.objects.filter(order_type='kiosk', status='pending')
    print(f"Pending kiosk orders: {pending_kiosk_orders.count()}")
    
    orders_data = []
    for order in pending_kiosk_orders:
        print(f"\n=== ORDER DETAIL: {order.order_id} ===")
        print(f"ID: {order.id}")
        print(f"Order ID: {order.order_id}")
        print(f"Hex ID: {order.hex_id}")
        print(f"Customer: {order.customer_name}")
        print(f"Total: {order.total_amount}")
        print(f"Status: {order.status}")
        print(f"Payment Method: {order.payment_method}")
        print(f"Created: {order.created_at}")
        
        # Check available related names for OrderItem
        related_names = []
        for field in order._meta.get_fields():
            if field.is_relation and field.related_model == OrderItem:
                related_names.append({
                    'name': field.name,
                    'related_name': getattr(field, 'related_name', None)
                })
        
        print(f"Available OrderItem related names: {[rn['name'] for rn in related_names]}")
        
        # Try different methods to get order items
        item_methods = {}
        
        # Method 1: orderitem_set (default Django)
        try:
            items_count = order.orderitem_set.count()
            item_methods['orderitem_set'] = {
                'count': items_count,
                'works': True
            }
            print(f"✓ orderitem_set: {items_count} items")
            
            # Show actual items if any
            if items_count > 0:
                for item in order.orderitem_set.all()[:3]:  # Show first 3 items
                    print(f"  - {item.quantity}x {item.cookie.name} = ₱{item.total_price}")
        except Exception as e:
            item_methods['orderitem_set'] = {
                'count': 0,
                'works': False,
                'error': str(e)
            }
            print(f"✗ orderitem_set error: {str(e)}")
        
        # Method 2: items (common custom name)
        try:
            items_count = order.items.count()
            item_methods['items'] = {
                'count': items_count,
                'works': True
            }
            print(f"✓ items: {items_count} items")
        except Exception as e:
            item_methods['items'] = {
                'count': 0,
                'works': False,
                'error': str(e)
            }
            print(f"✗ items error: {str(e)}")
        
        # Method 3: order_items (another common name)
        try:
            items_count = order.order_items.count()
            item_methods['order_items'] = {
                'count': items_count,
                'works': True
            }
            print(f"✓ order_items: {items_count} items")
        except Exception as e:
            item_methods['order_items'] = {
                'count': 0,
                'works': False,
                'error': str(e)
            }
            print(f"✗ order_items error: {str(e)}")
        
        # Method 4: Direct query (always works)
        direct_items = OrderItem.objects.filter(order=order)
        direct_count = direct_items.count()
        item_methods['direct_query'] = {
            'count': direct_count,
            'works': True
        }
        print(f"✓ Direct query: {direct_count} items")
        
        # Show items from direct query
        if direct_count > 0:
            for item in direct_items[:3]:  # Show first 3 items
                print(f"  - {item.quantity}x {item.cookie.name} = ₱{item.total_price}")
        else:
            print("  - No items found via direct query")
        
        # Determine which method works
        working_methods = [method for method, info in item_methods.items() if info['works']]
        print(f"Working methods: {working_methods}")
        
        order_data = {
            'id': order.id,
            'order_id': order.order_id,
            'hex_id': order.hex_id,
            'customer_name': order.customer_name,
            'total_amount': float(order.total_amount),
            'status': order.status,
            'payment_method': order.payment_method,
            'created_at': order.created_at.isoformat(),
            'related_names': related_names,
            'item_methods': item_methods,
            'working_methods': working_methods,
            'actual_item_count': direct_count
        }
        orders_data.append(order_data)
    
    # Check if there are any OrderItems at all
    total_order_items = OrderItem.objects.count()
    kiosk_order_items = OrderItem.objects.filter(order__order_type='kiosk').count()
    
    print(f"\n=== ORDERITEM STATS ===")
    print(f"Total OrderItems in system: {total_order_items}")
    print(f"Total OrderItems for kiosk orders: {kiosk_order_items}")
    
    # Sample some OrderItems to see structure
    if kiosk_order_items > 0:
        sample_items = OrderItem.objects.filter(order__order_type='kiosk')[:5]
        print("Sample OrderItems:")
        for item in sample_items:
            print(f"  - Order: {item.order.order_id} | Cookie: {item.cookie.name} | Qty: {item.quantity} | Price: {item.price}")
    
    return JsonResponse({
        'total_kiosk_orders': all_kiosk_orders.count(),
        'pending_kiosk_orders': pending_kiosk_orders.count(),
        'order_fields': order_fields,
        'orderitem_stats': {
            'total_orderitems': total_order_items,
            'kiosk_orderitems': kiosk_order_items
        },
        'pending_orders': orders_data,
        'debug_info': {
            'message': 'Check server console for detailed output',
            'working_methods_found': any(len(order['working_methods']) > 0 for order in orders_data)
        }
    })

# ==================== EXISTING PAYMENT REDIRECT FUNCTIONS (KEPT AS IS) ====================
def payment_redirect(request, order_id):
    """View for payment method redirection"""
    order = get_object_or_404(Order, id=order_id)
    
    # For now, redirect to order confirmation
    # You can add specific payment processing logic here later
    return redirect('staff_order_receipt', order_id=order_id)

def test_static(request):
    """Test if static files are working"""
    return render(request, 'test_static.html')

def test_auth(request):
    """Test view to check if user is authenticated"""
    return render(request, 'test_auth.html', {
        'user': request.user,
        'is_authenticated': request.user.is_authenticated,
        'groups': request.user.groups.all() if request.user.is_authenticated else []
    })

def debug_auth(request):
    """Debug view to check authentication status"""
    return render(request, 'debug_auth.html', {
        'user': request.user,
        'is_authenticated': request.user.is_authenticated,
        'path': request.path,
        'session_keys': list(request.session.keys()) if hasattr(request, 'session') else []
    })

@login_required
def debug_search(request):
    """Debug view to test search functionality"""
    query = request.GET.get('q', '')
    
    # Test the search logic
    if query:
        cookies = Cookie.objects.filter(
            Q(name__icontains=query) | 
            Q(flavor__icontains=query) |
            Q(description__icontains=query)
        ).order_by('name')
        result_count = cookies.count()
    else:
        cookies = Cookie.objects.all().order_by('name')
        result_count = cookies.count()
    
    # Test if Q object is working
    test_query = "Test Query"
    test_results = Cookie.objects.filter(Q(name__icontains=test_query))
    
    return render(request, 'debug_search.html', {
        'query': query,
        'result_count': result_count,
        'cookies': cookies,
        'test_query': test_query,
        'test_results_count': test_results.count(),
        'q_imported': 'Q' in globals(),
    })

@login_required
def debug_sales_search(request):
    """Debug view to test sales search functionality"""
    query = request.GET.get('q', '')
    
    # Test the search logic
    if query:
        cookies = Cookie.objects.filter(
            Q(name__icontains=query) | 
            Q(flavor__icontains=query)
        ).filter(stock_quantity__gt=0)
        result_count = cookies.count()
    else:
        cookies = Cookie.objects.filter(stock_quantity__gt=0)
        result_count = cookies.count()
    
    # Test if Q object is working
    test_query = "Test Query"
    test_results = Cookie.objects.filter(Q(name__icontains=test_query)).filter(stock_quantity__gt=0)
    
    return render(request, 'debug_sales_search.html', {
        'query': query,
        'result_count': result_count,
        'cookies': cookies,
        'test_query': test_query,
        'test_results_count': test_results.count(),
        'q_imported': 'Q' in globals(),
    })

@login_required
def test_data(request):
    """Test if there's data in the database"""
    cookie_count = Cookie.objects.count()
    available_cookies = Cookie.objects.filter(stock_quantity__gt=0).count()
    customer_count = Customer.objects.count()
    order_count = Order.objects.count()
    
    # Get some sample cookie names for testing
    sample_cookies = Cookie.objects.values_list('name', flat=True)[:5]
    
    return render(request, 'test_data.html', {
        'cookie_count': cookie_count,
        'available_cookies': available_cookies,
        'customer_count': customer_count,
        'order_count': order_count,
        'sample_cookies': list(sample_cookies),
    })

def debug_redirects(request):
    """Debug view to identify redirect loops"""
    print("=== REDIRECT DEBUG ===")
    print(f"User: {request.user}")
    print(f"Authenticated: {request.user.is_authenticated}")
    print(f"Path: {request.path}")
    print(f"Session keys: {list(request.session.keys())}")
    
    if request.user.is_authenticated:
        print("User is authenticated - checking profile...")
        if hasattr(request.user, 'profile'):
            print(f"User type: {request.user.profile.user_type}")
        else:
            print("No user profile found")
    
    return JsonResponse({
        'user': str(request.user),
        'authenticated': request.user.is_authenticated,
        'path': request.path,
        'session_keys': list(request.session.keys()),
    })

# ==================== EXISTING VOID ORDER FUNCTIONALITY (KEPT AS IS) ====================
@login_required
def void_order(request, order_id):
    """Void an order with permission-based admin confirmation"""
    print(f"VOID ORDER: Method={request.method}, OrderID={order_id}, User={request.user}")
    
    try:
        order = Order.objects.get(id=order_id)
        print(f"Order found: #{order.order_id}, Status: {order.status}, Staff: {order.staff}")
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
    
    if order.status == 'voided':
        if request.method == 'POST':
            return JsonResponse({'success': False, 'error': 'Order already voided'})
        else:
            return JsonResponse({
                'order_id': order.id,
                'total_amount': str(order.total_amount),
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
                'payment_method': order.get_payment_method_display(),
                'customer': order.customer_name if order.customer_name else 'Anonymous',
                'status': 'voided'
            })
    
    if request.method == 'POST':
        username = request.POST.get('admin_username')
        password = request.POST.get('admin_password')
        reason = request.POST.get('void_reason', '').strip()
        
        # Check if user can void without admin credentials
        if order.can_void(request.user):
            print(f"User {request.user} has permission to void order {order_id}")
            # User has permission, no admin credentials needed
            if not reason:
                return JsonResponse({'success': False, 'error': 'Reason required'})
            
            try:
                # Create void log
                void_log = VoidLog.objects.create(
                    order=order,
                    staff_member=request.user.staff if hasattr(request.user, 'staff') else None,
                    admin_user=None,  # No admin required since user has permission
                    reason=reason,
                    original_total=order.total_amount,
                    original_payment_method=order.payment_method
                )
                
                # Restore inventory
                for item in order.items.all():
                    cookie = item.cookie
                    cookie.stock_quantity += item.quantity
                    cookie.save()
                
                # Update order status
                order.status = 'voided'
                order.save()
                
                # Log activity
                log_activity(
                    user=request.user,
                    action='order_voided',
                    description=f'Voided order #{order.order_id} - Reason: {reason}',
                    ip_address=get_client_ip(request),
                    affected_model='Order',
                    affected_id=order.id
                )
                
                return JsonResponse({
                    'success': True,
                    'message': f'Order #{order.order_id} voided successfully. Void ID: {void_log.void_id}',
                    'void_id': void_log.void_id,
                    'admin_required': False
                })
                
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'Error: {str(e)}'})
        
        else:
            # User doesn't have permission, require admin credentials
            print(f"User {request.user} needs admin approval to void order {order_id}")
            
            if not username or not password:
                return JsonResponse({'success': False, 'error': 'Admin credentials required for voiding this order'})
            
            if not reason:
                return JsonResponse({'success': False, 'error': 'Reason required'})
            
            # Authenticate admin
            admin_user = authenticate(request, username=username, password=password)
            if not admin_user:
                return JsonResponse({'success': False, 'error': 'Invalid admin credentials'})
            
            # Check admin privileges
            if not (admin_user.is_superuser or (hasattr(admin_user, 'staff') and admin_user.staff.role == 'admin')):
                return JsonResponse({'success': False, 'error': 'Admin privileges required'})
            
            try:
                # Create void log
                void_log = VoidLog.objects.create(
                    order=order,
                    staff_member=request.user.staff if hasattr(request.user, 'staff') else None,
                    admin_user=admin_user,
                    reason=reason,
                    original_total=order.total_amount,
                    original_payment_method=order.payment_method
                )
                
                # Restore inventory
                for item in order.items.all():
                    cookie = item.cookie
                    cookie.stock_quantity += item.quantity
                    cookie.save()
                
                # Update order status
                order.status = 'voided'
                order.save()
                
                # Log activity
                log_activity(
                    user=request.user,
                    action='order_voided',
                    description=f'Voided order #{order.order_id} - Reason: {reason} (Admin approved)',
                    ip_address=get_client_ip(request),
                    affected_model='Order',
                    affected_id=order.id
                )
                
                return JsonResponse({
                    'success': True,
                    'message': f'Order #{order.order_id} voided successfully with admin approval. Void ID: {void_log.void_id}',
                    'void_id': void_log.void_id,
                    'admin_required': True
                })
                
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'Error: {str(e)}'})
    
    # GET request - Return order details and permission info
    can_void_directly = order.can_void(request.user)
    
    return JsonResponse({
        'order_id': order.id,
        'order_display_id': order.order_id,
        'total_amount': str(order.total_amount),
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
        'payment_method': order.get_payment_method_display(),
        'customer': order.customer_name if order.customer_name else 'Anonymous',
        'status': 'completed',
        'can_void_directly': can_void_directly,
        'current_user_is_owner': request.user == order.staff,
        'current_user_is_admin': request.user.is_superuser or (hasattr(request.user, 'staff') and request.user.staff.role == 'admin')
    })

def void_modal(request):
    """Serve the void modal template"""
    return render(request, 'void_modal.html')

@login_required
def debug_void_system(request):
    """Debug view to test void system"""
    orders = Order.objects.filter(status='completed')[:5]
    debug_info = {
        'orders_available': [{'id': o.id, 'order_id': o.order_id, 'total': str(o.total_amount)} for o in orders],
        'user_is_admin': request.user.is_superuser or (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'),
        'csrf_token_working': bool(getattr(request, 'csrf_processing_done', False)),
    }
    return JsonResponse(debug_info)

@login_required
def debug_void_process(request, order_id):
    """Debug view to test void process"""
    order = get_object_or_404(Order, id=order_id)
    
    debug_info = {
        'order_exists': True,
        'order_id': order.id,
        'order_display_id': order.order_id,
        'order_status': order.status,
        'order_total': str(order.total_amount),
        'user_has_staff': hasattr(request.user, 'staff'),
        'user_staff_role': getattr(request.user.staff, 'role', 'No staff') if hasattr(request.user, 'staff') else 'No staff',
        'is_admin': request.user.is_superuser or (hasattr(request.user, 'staff') and request.user.staff.role == 'admin'),
        'order_items_count': order.items.count(),
        'void_logs_exist': hasattr(order, 'void_logs') and order.void_logs.exists(),
    }
    
    return JsonResponse(debug_info)

@login_required
@customer_required
def payment_confirm(request, order_id):
    """Payment confirmation page - placeholder function"""
    customer = request.user.profile.customer
    order = get_object_or_404(Order, id=order_id, customer=customer)

    # For demo purposes - mark as paid
    order.is_paid = True
    order.paid_at = timezone.now()
    order.status = 'completed'
    order.save()

    messages.success(request, f'Payment confirmed! Your order is now being processed.')
    return redirect('staff_order_receipt', order_id=order.id)

@login_required
@customer_required
@ensure_csrf_cookie
@csrf_protect
def place_order(request):
    """Customer order placement - using unified Order model"""
    customer = request.user.profile.customer
    available_cookies = Cookie.objects.filter(stock_quantity__gt=0, is_available=True).select_related('category')
    
    categories = Category.objects.filter(cookies__in=available_cookies).distinct()
    
    cookies_by_category = {}
    for cookie in available_cookies:
        if cookie.category:
            category_display = cookie.category.name
        else:
            category_display = 'Other'
        
        if category_display not in cookies_by_category:
            cookies_by_category[category_display] = []
        cookies_by_category[category_display].append(cookie)
    
    # Get cart items from session to pre-populate the order summary
    cart_items, cart_total, cart_map = _get_session_cart_items(request)
    
    if request.method == 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                # Use session cart items instead of client-side items
                order_items = cart_map  # This is the session cart
                total_amount = cart_total
                notes = request.POST.get('notes', '')
                payment_method = (request.POST.get('payment_method') or '').strip().lower()
                
                print(f"DEBUG: Cart items: {order_items}")  # Debug
                print(f"DEBUG: Total amount: {total_amount}")  # Debug
                print(f"DEBUG: Payment method: {payment_method}")  # Debug
                
                if not order_items:
                    return JsonResponse({'success': False, 'error': 'No items in order.'})
                
                # Validate stock before creating order
                for cookie_id, quantity in order_items.items():
                    if int(quantity) > 0:
                        try:
                            cookie = Cookie.objects.get(id=int(cookie_id))
                            if cookie.stock_quantity < int(quantity):
                                return JsonResponse({
                                    'success': False, 
                                    'error': f'Not enough stock for {cookie.name}. Only {cookie.stock_quantity} available.'
                                })
                        except Cookie.DoesNotExist:
                            return JsonResponse({
                                'success': False,
                                'error': f'Cookie with ID {cookie_id} not found.'
                            })
                
                # Create order
                order = Order.objects.create(
                    customer=customer,
                    customer_name=customer.name,
                    customer_phone=customer.phone or '',
                    total_amount=total_amount,
                    notes=notes,
                    status='pending',  
                    payment_method=payment_method or 'cash',
                    order_type='kiosk'
                )

                # If customer selected GCash, attach optional screenshot and leave as unpaid for manual verification
                if payment_method == 'gcash':
                    gcash_file = request.FILES.get('gcash_screenshot')
                    if gcash_file:
                        order.gcash_screenshot = gcash_file
                    order.is_paid = False
                    order.save()
                
                # Create order items and update stock
                for cookie_id, quantity in order_items.items():
                    if int(quantity) > 0:
                        cookie = Cookie.objects.get(id=int(cookie_id))
                        OrderItem.objects.create(
                            order=order,
                            cookie=cookie,
                            quantity=int(quantity),
                            price=cookie.price
                        )
                        # Update stock
                        cookie.stock_quantity -= int(quantity)
                        cookie.save()
                
                # Clear the cart after successful order
                request.session['cart'] = {}
                request.session.modified = True
                
                # Log activity
                log_activity(
                    user=request.user,
                    action='order_created',
                    description=f'Customer order created: {order.order_id} - ₱{total_amount:.2f}',
                    ip_address=get_client_ip(request),
                    affected_model='Order',
                    affected_id=order.id
                )
                
                return JsonResponse({
                    'success': True,
                    'order_id': order.id,
                    'redirect_url': f'/app/customer/order-confirmation/{order.id}/',
                    'message': 'Order placed successfully!'
                })
                
            except Exception as e:
                print(f"Error in place_order: {str(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")  # More detailed error
                return JsonResponse({'success': False, 'error': str(e)})
        else:
            return JsonResponse({'success': False, 'error': 'Invalid request type'})
    
    # GET request - render the template with cart items
    context = {
        'available_cookies': available_cookies,
        'cookies_by_category': cookies_by_category,
        'categories': categories,
        'customer': customer,
        'cart_items': cart_items,
        'cart_total': cart_total,
    }
    return render(request, 'customer/place_order.html', context)

@login_required
@customer_required
def order_confirmation(request, order_id):
    """Order confirmation page for customers"""
    try:
        order = get_object_or_404(Order, id=order_id, customer=request.user.profile.customer)
        
        # Get order items with calculated totals - FIXED VERSION
        items = []
        for item in order.items.all().select_related('cookie'):
            # Create a dictionary with the item data including calculated total
            item_data = {
                'cookie': item.cookie,
                'quantity': item.quantity,
                'price': item.price,
                'total_price': item.quantity * item.price  # Calculate total here
            }
            items.append(item_data)
        
        context = {
            'order': order,
            'items': items,  # Now using list of dictionaries instead of model instances
            'customer': request.user.profile.customer
        }
        return render(request, 'customer/order_confirmation.html', context)
    except Exception as e:
        messages.error(request, f'Error loading order confirmation: {str(e)}')
        return redirect('customer_dashboard')

def debug_urls(request):
    url_patterns = []
    resolver = get_resolver()
    for pattern in resolver.url_patterns:
        if hasattr(pattern, 'name') and pattern.name:
            url_patterns.append(pattern.name)
    return JsonResponse({'url_names': sorted(url_patterns)})

@login_required
def debug_user_status(request):
    """Debug view to check user status after OAuth login"""
    user = request.user
    debug_info = {
        'username': user.username,
        'email': user.email,
        'is_authenticated': user.is_authenticated,
        'is_superuser': user.is_superuser,
        'is_staff': user.is_staff,
        'has_profile': hasattr(user, 'profile'),
        'user_type': getattr(user.profile, 'user_type', 'NO PROFILE') if hasattr(user, 'profile') else 'NO PROFILE',
        'has_customer': hasattr(user.profile, 'customer') if hasattr(user, 'profile') else False,
        'has_staff': hasattr(user, 'staff'),
        'staff_role': getattr(user.staff, 'role', 'NO STAFF') if hasattr(user, 'staff') else 'NO STAFF',
        'staff_is_active': getattr(user.staff, 'is_active', False) if hasattr(user, 'staff') else False,
    }
    
    # Log for debugging
    logger.info(f"User Status Debug: {debug_info}")
    
    return JsonResponse(debug_info)

@login_required
@staff_required
def staff_dashboard_debug(request):
    """Debug endpoint to check real-time data"""
    today = timezone.now().date()
    staff = request.user
    
    debug_data = {
        'staff': staff.username,
        'today': today.isoformat(),
        'timestamp': timezone.now().isoformat(),
    }
    
    try:
        staff_orders_today = Order.objects.filter(
            staff=staff,
            created_at__date=today
        )
        
        completed_orders_today = staff_orders_today.filter(status='completed')
        pending_orders_today = staff_orders_today.filter(status='pending')
        
        debug_data.update({
            'total_orders_count': staff_orders_today.count(),
            'completed_orders_count': completed_orders_today.count(),
            'pending_orders_count': pending_orders_today.count(),
            'orders_debug': list(staff_orders_today.values('order_id', 'status', 'created_at')[:5]),
            'success': True
        })
        
    except Exception as e:
        debug_data.update({
            'error': str(e),
            'success': False
        })
    
    return JsonResponse(debug_data)
# Add these functions to your views.py file

@login_required
@customer_required
def process_cash_payment(request, order_id=None):
    """Process cash payment for customer orders"""
    if order_id:
        order = get_object_or_404(Order, id=order_id, customer=request.user.profile.customer)
    else:
        messages.error(request, "No order specified for payment.")
        return redirect('customer_dashboard')
    
    if request.method == 'POST':
        try:
            # Mark order as paid
            order.status = 'completed'
            order.is_paid = True
            order.paid_at = timezone.now()
            order.payment_method = 'cash'
            order.save()
            
            # Add loyalty points
            if order.customer:
                points_earned = int(order.total_amount)
                order.customer.loyalty_points += points_earned
                order.customer.save()
            
            log_activity(
                user=request.user,
                action='order_completed',
                description=f'Cash payment completed for order: {order.order_id}',
                ip_address=get_client_ip(request),
                affected_model='Order',
                affected_id=order.id
            )
            
            messages.success(request, f'Cash payment processed successfully! Order #{order.order_id}')
            return redirect('staff_order_receipt', order_id=order.id)
            
        except Exception as e:
            messages.error(request, f'Error processing payment: {str(e)}')
    
    return render(request, 'customer/process_cash_payment.html', {'order': order})

@login_required
@customer_required
def process_gcash_payment(request, order_id):
    """Process GCash payment - placeholder for integration"""
    order = get_object_or_404(Order, id=order_id, customer=request.user.profile.customer)
    
    if request.method == 'POST':
        # Simulate GCash payment processing
        order.status = 'completed'
        order.is_paid = True
        order.paid_at = timezone.now()
        order.payment_method = 'gcash'
        order.save()
        
        messages.success(request, f'GCash payment processed successfully! Order #{order.order_id}')
        return redirect('staff_order_receipt', order_id=order.id)
    
    return render(request, 'customer/process_gcash_payment.html', {'order': order})

@login_required
@customer_required
def process_card_payment(request, order_id):
    """Process card payment - placeholder for integration"""
    order = get_object_or_404(Order, id=order_id, customer=request.user.profile.customer)
    
    if request.method == 'POST':
        # Simulate card payment processing
        order.status = 'completed'
        order.is_paid = True
        order.paid_at = timezone.now()
        order.payment_method = 'card'
        order.save()
        
        messages.success(request, f'Card payment processed successfully! Order #{order.order_id}')
        return redirect('staff_order_receipt', order_id=order.id)
    
    return render(request, 'customer/process_card_payment.html', {'order': order})

@login_required
@customer_required
def process_maya_payment(request, order_id):
    """Process Maya payment - placeholder for integration"""
    order = get_object_or_404(Order, id=order_id, customer=request.user.profile.customer)
    
    if request.method == 'POST':
        # Simulate Maya payment processing
        order.status = 'completed'
        order.is_paid = True
        order.paid_at = timezone.now()
        order.payment_method = 'maya'
        order.save()
        
        messages.success(request, f'Maya payment processed successfully! Order #{order.order_id}')
        return redirect('staff_order_receipt', order_id=order.id)
    
    return render(request, 'customer/process_maya_payment.html', {'order': order})
# ==================== HELPER FUNCTIONS ====================
def is_admin_user(user):
    """Check if user is admin (superuser or admin role)"""
    if user.is_superuser:
        return True
    if hasattr(user, 'staff'):
        return user.staff.role == 'admin'
    return False

@login_required
@staff_required
def order_create(request):
    """Create a new order - redirects to record sale for now"""
    messages.info(request, "Use the Record Sale page to create new orders.")
    return redirect('staff_record_sale')

@login_required
@staff_required
def order_detail(request, order_id):
    """View order details - supports both HTML and JSON responses"""
    order = get_object_or_404(Order, id=order_id)
    
    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
        try:
            order_data = {
                'success': True,
                'order': {
                    'id': order.id,
                    'order_id': order.order_id,
                    'customer_name': order.customer_name,
                    'status': order.status,
                    'status_display': order.get_status_display(),
                    'payment_method': order.payment_method,
                    'payment_method_display': order.get_payment_method_display(),
                    'total_amount': str(order.total_amount),
                    'created_at': order.created_at.isoformat(),
                    'items': [
                        {
                            'cookie_name': item.cookie.name,
                            'quantity': item.quantity,
                            'price': str(item.price),
                        }
                        for item in order.items.all()
                    ]
                }
            }
            return JsonResponse(order_data)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    # Regular HTML response
    order = Order.objects.select_related(
        'customer', 
        'staff', 
        'customer__user_profile'
    ).prefetch_related(
        'items',
        'items__cookie'
    ).get(id=order_id)
    
    return render(request, 'orders/order_detail.html', {
        'order': order
    })

@login_required
@staff_required
def search_kiosk_orders(request):
    """API endpoint for searching pending kiosk orders"""
    query = request.GET.get('q', '').strip()
    
    print(f"=== KIOSK ORDER SEARCH ===")
    print(f"Search query: '{query}'")
    
    if len(query) < 2:
        print("Query too short, returning empty results")
        return JsonResponse({'results': []})
    
    try:
        # Search for PENDING kiosk orders
        kiosk_orders = Order.objects.filter(
            order_type='kiosk',
            status='pending'
        ).filter(
            Q(order_id__icontains=query) |
            Q(hex_id__icontains=query) |
            Q(customer_name__icontains=query)
        ).order_by('-created_at')[:10]  # Show most recent first
        
        print(f"Found {kiosk_orders.count()} pending kiosk orders matching '{query}'")
        
        results = []
        for order in kiosk_orders:
            # Get the related name dynamically
            if hasattr(order, 'orderitem_set'):
                item_count = order.orderitem_set.count()
            elif hasattr(order, 'items'):
                item_count = order.items.count()
            else:
                item_count = OrderItem.objects.filter(order=order).count()
                
            order_data = {
                'id': order.id,
                'order_id': order.order_id,
                'hex_id': order.hex_id or 'N/A',
                'customer_name': order.customer_name or 'Kiosk Customer',
                'total_amount': str(order.total_amount),
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
                'payment_method': order.payment_method or 'cash',
                'item_count': item_count,
                'display_text': f"{order.order_id} - {order.customer_name} - ₱{order.total_amount:.2f} - {item_count} items"
            }
            results.append(order_data)
            print(f"  - {order_data['display_text']}")
        
        print(f"Returning {len(results)} results")
        
        return JsonResponse({'results': results})
    
    except Exception as e:
        print(f"Error searching kiosk orders: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'results': [], 'error': str(e)})

@login_required
@staff_required
def kiosk_order_items(request, order_id):
    """API endpoint to get kiosk order items"""
    try:
        order = Order.objects.get(id=order_id, order_type='kiosk')
        
        print(f"=== LOADING KIOSK ORDER ITEMS ===")
        print(f"Order: {order.order_id}")
        
        # Try different related names to find the correct one
        items = None
        if hasattr(order, 'orderitem_set'):
            print("Using orderitem_set relation")
            items = order.orderitem_set.select_related('cookie')
        elif hasattr(order, 'items'):
            print("Using items relation")
            items = order.items.select_related('cookie')
        elif hasattr(order, 'order_items'):
            print("Using order_items relation")
            items = order.order_items.select_related('cookie')
        else:
            print("Using direct OrderItem query")
            items = OrderItem.objects.filter(order=order).select_related('cookie')
        
        if items is None:
            items = OrderItem.objects.filter(order=order).select_related('cookie')
        
        item_list = []
        for item in items:
            item_data = {
                'cookie_name': item.cookie.name,
                'quantity': item.quantity,
                'price': str(item.price),
                'total': str(item.total_price)
            }
            item_list.append(item_data)
            print(f"  - {item.quantity}x {item.cookie.name} = ₱{item.total_price}")
        
        print(f"Found {len(item_list)} items")
        
        return JsonResponse({'items': item_list})
        
    except Order.DoesNotExist:
        print(f"Order {order_id} not found")
        return JsonResponse({'items': [], 'error': 'Order not found'}, status=404)
    except Exception as e:
        print(f"Error loading kiosk order items: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'items': [], 'error': str(e)}, status=500)
    
@login_required
@staff_required
def staff_dashboard_realtime_data(request):
    """AJAX endpoint for real-time staff dashboard data - FIXED VERSION"""
    today = timezone.now().date()
    staff = request.user
    
    try:
        # FIX: Use created_at__date for today's orders, not completed_at
        staff_orders_today = Order.objects.filter(
            staff=staff,
            created_at__date=today  # This gets all orders created today
        )
        
        # FIX: Completed orders should also be from today
        completed_orders_today = staff_orders_today.filter(status='completed')
        pending_orders_today = staff_orders_today.filter(status='pending')
        
        total_sales_today = completed_orders_today.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        orders_count_today = staff_orders_today.count()
        completed_count_today = completed_orders_today.count()
        pending_orders_count = pending_orders_today.count()
        
        # FIX: Recent completed orders should be from today
        recent_completed_orders = completed_orders_today.select_related('customer').order_by('-completed_at')[:5]
        
        # FIX: Recent all orders should be from today
        recent_staff_orders = staff_orders_today.order_by('-created_at')[:10]
        
        # Monthly performance (completed orders this month)
        month_start = today.replace(day=1)
        monthly_completed = Order.objects.filter(
            staff=staff,
            status='completed',
            completed_at__date__gte=month_start  # Use completed_at for monthly
        )
        monthly_sales = monthly_completed.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        monthly_orders = monthly_completed.count()
        
        # Format recent orders for JSON
        recent_completed_data = []
        for order in recent_completed_orders:
            recent_completed_data.append({
                'order_id': order.order_id,
                'customer_name': order.customer_name or "Walk-in",
                'total_amount': float(order.total_amount),
                'completed_at': order.completed_at.strftime("%b %d, %H:%M") if order.completed_at else "",
                'order_type': order.get_order_type_display(),
                'payment_method': order.payment_method
            })
        
        recent_orders_data = []
        for order in recent_staff_orders:
            recent_orders_data.append({
                'order_id': order.order_id,
                'customer_name': order.customer_name or "Walk-in",
                'total_amount': float(order.total_amount),
                'status': order.status,
                'created_at': order.created_at.strftime("%b %d, %H:%M"),
                'order_type': order.get_order_type_display()
            })
        
        data = {
            'success': True,
            'data': {
                'total_sales_today': float(total_sales_today),
                'orders_count_today': orders_count_today,
                'completed_count_today': completed_count_today,
                'pending_orders_count': pending_orders_count,
                'monthly_sales': float(monthly_sales),
                'monthly_orders': monthly_orders,
                'completion_rate': (completed_count_today / orders_count_today * 100) if orders_count_today > 0 else 0,
                'recent_completed_orders': recent_completed_data,
                'recent_orders': recent_orders_data,
                'timestamp': timezone.now().strftime("%H:%M:%S"),
                'debug': {
                    'today': today.isoformat(),
                    'total_orders_query': orders_count_today,
                    'completed_query': completed_count_today
                }
            }
        }
        
    except Exception as e:
        data = {
            'success': False,
            'error': str(e),
            'data': {
                'total_sales_today': 0.00,
                'orders_count_today': 0,
                'completed_count_today': 0,
                'pending_orders_count': 0,
                'monthly_sales': 0.00,
                'monthly_orders': 0,
                'completion_rate': 0,
                'recent_completed_orders': [],
                'recent_orders': [],
                'timestamp': timezone.now().strftime("%H:%M:%S")
            }
        }
    
    return JsonResponse(data)

@login_required
@staff_required  
def staff_new_orders_check(request):
    """Check for new orders since last update"""
    last_check = request.GET.get('last_check')
    staff = request.user
    
    try:
        # Get new completed orders
        new_completed_query = Order.objects.filter(
            staff=staff,
            status='completed'
        )
        
        # Get new all orders
        new_orders_query = Order.objects.filter(staff=staff)
        
        if last_check:
            try:
                last_check_dt = timezone.datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                new_completed_query = new_completed_query.filter(completed_at__gt=last_check_dt)
                new_orders_query = new_orders_query.filter(created_at__gt=last_check_dt)
            except (ValueError, AttributeError):
                pass
        
        new_completed_count = new_completed_query.count()
        new_orders_count = new_orders_query.count()
        
        # Get the actual new orders for notifications
        new_completed_orders = new_completed_query.order_by('-completed_at')[:3]
        new_orders = new_orders_query.order_by('-created_at')[:3]
        
        completed_orders_data = []
        for order in new_completed_orders:
            completed_orders_data.append({
                'order_id': order.order_id,
                'customer_name': order.customer_name or "Walk-in", 
                'total_amount': float(order.total_amount),
                'completed_at': order.completed_at.strftime("%H:%M") if order.completed_at else ""
            })
            
        orders_data = []
        for order in new_orders:
            orders_data.append({
                'order_id': order.order_id,
                'customer_name': order.customer_name or "Walk-in",
                'total_amount': float(order.total_amount),
                'status': order.status,
                'created_at': order.created_at.strftime("%H:%M")
            })
        
        data = {
            'success': True,
            'has_updates': new_completed_count > 0 or new_orders_count > 0,
            'new_completed_count': new_completed_count,
            'new_orders_count': new_orders_count,
            'new_completed_orders': completed_orders_data,
            'new_orders': orders_data,
            'current_time': timezone.now().isoformat()
        }
        
    except Exception as e:
        data = {
            'success': False,
            'error': str(e),
            'has_updates': False,
            'new_completed_count': 0,
            'new_orders_count': 0,
            'new_completed_orders': [],
            'new_orders': [],
            'current_time': timezone.now().isoformat()
        }
    
    return JsonResponse(data)
@login_required
@staff_required
def sales_report_realtime_data(request):
    """AJAX endpoint for real-time sales report data"""
    try:
        today = timezone.now().date()
        start_date = request.GET.get('start_date', today)
        end_date = request.GET.get('end_date', today)
        
        # Convert string dates to date objects
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get current data
        all_orders = Order.objects.filter(
            created_at__date__range=[start_date, end_date]
        )
        completed_orders = all_orders.filter(status='completed')
        
        # Calculate real-time stats
        total_sales = all_orders.aggregate(
            total_amount=Sum('total_amount'),
            total_orders=Count('id')
        )
        
        kiosk_orders = all_orders.filter(order_type='kiosk')
        walkin_orders = all_orders.filter(order_type='staff')
        
        order_type_stats = {
            'kiosk': {
                'count': kiosk_orders.count(),
                'revenue': float(kiosk_orders.aggregate(total=Sum('total_amount'))['total'] or 0),
            },
            'walkin': {
                'count': walkin_orders.count(),
                'revenue': float(walkin_orders.aggregate(total=Sum('total_amount'))['total'] or 0),
            }
        }
        
        # Calculate pie chart percentages
        total_count = order_type_stats['kiosk']['count'] + order_type_stats['walkin']['count']
        if total_count > 0:
            walkin_percent = (order_type_stats['walkin']['count'] / total_count) * 100
            kiosk_percent = (order_type_stats['kiosk']['count'] / total_count) * 100
        else:
            walkin_percent = 0
            kiosk_percent = 0
        
        data = {
            'success': True,
            'data': {
                'total_sales': {
                    'total_amount': float(total_sales['total_amount'] or 0),
                    'total_orders': total_sales['total_orders'] or 0
                },
                'order_type_stats': order_type_stats,
                'completion_stats': {
                    'total_orders': all_orders.count(),
                    'completed_orders': completed_orders.count(),
                    'completion_rate': (completed_orders.count() / all_orders.count() * 100) if all_orders.count() > 0 else 0
                },
                'pie_chart': {
                    'walkin_percent': round(walkin_percent, 1),
                    'kiosk_percent': round(kiosk_percent, 1),
                    'walkin_count': order_type_stats['walkin']['count'],
                    'kiosk_count': order_type_stats['kiosk']['count']
                },
                'timestamp': timezone.now().strftime("%H:%M:%S")
            }
        }
        
    except Exception as e:
        data = {
            'success': False,
            'error': str(e),
            'data': {
                'total_sales': {'total_amount': 0, 'total_orders': 0},
                'order_type_stats': {
                    'kiosk': {'count': 0, 'revenue': 0},
                    'walkin': {'count': 0, 'revenue': 0}
                },
                'completion_stats': {'total_orders': 0, 'completed_orders': 0, 'completion_rate': 0},
                'pie_chart': {'walkin_percent': 0, 'kiosk_percent': 0, 'walkin_count': 0, 'kiosk_count': 0},
                'timestamp': timezone.now().strftime("%H:%M:%S")
            }
        }
    
    return JsonResponse(data)

@login_required
@staff_required
def sales_report_new_orders_check(request):
    """Check for new orders since last update"""
    last_check = request.GET.get('last_check')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    try:
        # Convert dates
        today = timezone.now().date()
        if start_date and isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = today
            
        if end_date and isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = today
        
        # Check for new orders
        new_orders_query = Order.objects.filter(
            created_at__date__range=[start_date, end_date]
        )
        
        if last_check:
            try:
                last_check_dt = timezone.datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                new_orders_query = new_orders_query.filter(created_at__gt=last_check_dt)
            except (ValueError, AttributeError):
                pass
        
        new_orders_count = new_orders_query.count()
        
        data = {
            'success': True,
            'has_updates': new_orders_count > 0,
            'new_orders_count': new_orders_count,
            'current_time': timezone.now().isoformat()
        }
        
    except Exception as e:
        data = {
            'success': False,
            'error': str(e),
            'has_updates': False,
            'new_orders_count': 0,
            'current_time': timezone.now().isoformat()
        }
    
    return JsonResponse(data)

# Add this to views.py temporarily
@login_required
@staff_required
def check_cash_fields(request):
    """Temporary view to check cash field status"""
    orders = Order.objects.all()[:10]  # Check first 10 orders
    
    results = []
    for order in orders:
        results.append({
            'order_id': order.order_id,
            'payment_method': order.payment_method,
            'total_amount': order.total_amount,
            'cash_received': order.cash_received,
            'change': order.change,
            'has_cash_received': order.cash_received is not None,
        })
    
    return JsonResponse({'orders': results})


# ==================== EMAIL VERIFICATION ====================

def send_verification_email(customer, request):
    """Send email verification link to customer"""
    from django.core.mail import send_mail
    from django.urls import reverse
    
    verification_url = request.build_absolute_uri(
        reverse('verify_email', kwargs={'token': customer.email_verification_token})
    )
    
    subject = 'Verify Your Email - Cookie Craze'
    message = f"""
    Hello {customer.name},

    Thank you for registering with Cookie Craze! To complete your registration and start ordering, 
    please verify your email address by clicking the link below:

    {verification_url}

    This link will expire in 24 hours.

    If you didn't create this account, please ignore this email.

    Best regards,
    Cookie Craze Team
    """
    
    try:
        send_mail(
            subject,
            message,
            'noreply@cookiecraze.com',
            [customer.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending verification email: {e}")
        return False


@csrf_protect
def verify_email(request, token):
    """Verify customer email using token"""
    try:
        customer = Customer.objects.get(email_verification_token=token)
        
        # Check if token is still valid (24 hours)
        if customer.email_verification_sent_at:
            from datetime import timedelta
            expiry_time = customer.email_verification_sent_at + timedelta(hours=24)
            if timezone.now() > expiry_time:
                messages.error(request, 'Verification link has expired. Please request a new one.')
                return redirect('home')
        
        # Mark email as verified
        customer.is_email_verified = True
        customer.email_verified_at = timezone.now()
        customer.email_verification_token = None
        customer.save()
        
        # Activate the user account
        customer.user_profile.user.is_active = True
        customer.user_profile.user.save()
        
        # Log activity
        log_activity(
            user=customer.user_profile.user,
            action='email_verified',
            description=f'Customer email verified: {customer.email}',
            ip_address=get_client_ip(request)
        )
        
        messages.success(request, 'Email verified successfully! You can now log in.')
        return redirect('home')
        
    except Customer.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
        return redirect('home')
    except Exception as e:
        print(f"Error verifying email: {e}")
        messages.error(request, 'An error occurred while verifying your email.')
        return redirect('home')


@login_required
@customer_required
def resend_verification_email(request):
    """Resend verification email to customer"""
    try:
        customer = request.user.profile.customer
        
        if customer.is_email_verified:
            messages.info(request, 'Your email is already verified.')
            return redirect('customer_dashboard')
        
        # Generate new token
        import secrets
        customer.email_verification_token = secrets.token_urlsafe(48)
        customer.email_verification_sent_at = timezone.now()
        customer.save()
        
        # Send email
        if send_verification_email(customer, request):
            messages.success(request, 'Verification email sent! Please check your inbox.')
            log_activity(
                user=request.user,
                action='resend_verification',
                description=f'Verification email resent to: {customer.email}',
                ip_address=get_client_ip(request)
            )
        else:
            messages.error(request, 'Failed to send verification email. Please try again.')
        
        return redirect('home')
        
    except Exception as e:
        print(f"Error resending verification email: {e}")
        messages.error(request, 'An error occurred.')
        return redirect('home')


# ==================== FTUE (First Time User Experience) ====================

