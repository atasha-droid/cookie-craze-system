# cookie_app/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid
import secrets

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=7, default='#007bff')
    icon = models.CharField(max_length=50, default='fas fa-folder')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def get_cookie_count(self):
        """Return count of cookies in this category"""
        return self.cookies.count()
    
    def __str__(self):
        return self.name

class Cookie(models.Model):
    FLAVOR_CHOICES = [
        ('chocolate', 'Chocolate'), ('vanilla', 'Vanilla'), ('strawberry', 'Strawberry'),
        ('oatmeal', 'Oatmeal'), ('peanut_butter', 'Peanut Butter'), ('butter', 'Butter'),
        ('white_chocolate', 'White Chocolate'), ('almond', 'Almond'), ('pistachio', 'Pistachio'),
        ('caramel', 'Caramel'), ('mint_chocolate', 'Mint Chocolate'), ('cream_cheese', 'Cream Cheese'),
        ('spice', 'Spice'), ('ube', 'Ube'), ('matcha', 'Matcha'),
        ('chocolate_hazelnut', 'Chocolate Hazelnut'), ('chocolate_marshmallow', 'Chocolate Marshmallow'),
        ('almond_oat', 'Almond Oat'),
    ]
    
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='cookies')
    image = models.ImageField(upload_to='cookies/', null=True, blank=True)
    name = models.CharField(max_length=100)
    flavor = models.CharField(max_length=30, choices=FLAVOR_CHOICES)
    price = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    stock_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    description = models.TextField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - ₱{self.price}"

class UserProfile(models.Model):
    USER_TYPES = [('customer', 'Customer'), ('staff', 'Staff'), ('admin', 'Administrator')]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='customer')
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    customer_id = models.CharField(max_length=16, unique=True, blank=True, null=True)
    loyalty_points = models.IntegerField(default=0)
    
    def save(self, *args, **kwargs):
        if not self.customer_id and self.user_type == 'customer':
            while True:
                cust_id = f"CUST{secrets.randbelow(900000) + 100000:06d}"
                if not UserProfile.objects.filter(customer_id=cust_id).exists():
                    self.customer_id = cust_id
                    break
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.username} ({self.get_user_type_display()})"

class Customer(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='customer')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField()
    loyalty_points = models.IntegerField(default=0)
    date_joined = models.DateTimeField(auto_now_add=True)
    ftue_completed = models.BooleanField(default=False)
    
    # Email verification fields
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.user_profile.customer_id})"

class Staff(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'), 
        ('manager', 'Manager'),
        ('staff', 'Staff Member'), 
        ('pending', 'Pending Approval')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff')
    staff_id = models.CharField(max_length=20, unique=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='pending')
    is_active = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.staff_id:
            while True:
                staff_id = f"STAFF{secrets.randbelow(9000) + 1000:04d}"
                if not Staff.objects.filter(staff_id=staff_id).exists():
                    self.staff_id = staff_id
                    break
        
        # Update UserProfile when staff is created/updated
        profile, created = UserProfile.objects.get_or_create(user=self.user)
        if self.role != 'pending' and self.is_active:
            profile.user_type = 'staff' if self.role == 'staff' else 'admin'
            profile.save()
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} ({self.staff_id})"

    @property
    def display_name(self):
        return f"{self.user.get_full_name() or self.user.username}"

    @property
    def email(self):
        return self.user.email


class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Order(models.Model):
    ORDER_TYPES = [('kiosk', 'Kiosk Order'), ('staff', 'Staff Recorded')]
    PAYMENT_METHODS = [('cash', 'Cash'), ('gcash', 'GCash')]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('completed', 'Completed'),
        ('voided', 'Voided'),
        ('cancelled', 'Cancelled')
    ]
    
    order_id = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    customer_name = models.CharField(max_length=100, blank=True, null=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    hex_id = models.CharField(max_length=8, unique=True, blank=True, editable=False)
    staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_orders')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    order_type = models.CharField(max_length=10, choices=ORDER_TYPES, default='kiosk')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='gcash')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_daily_report = models.BooleanField(default=False)
    report_date = models.DateField(null=True, blank=True)
    # Manual GCash verification fields
    gcash_reference = models.CharField(max_length=64, null=True, blank=True)
    gcash_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gcash_verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='gcash_verified_orders')
    gcash_verified_at = models.DateTimeField(null=True, blank=True)
    gcash_screenshot = models.ImageField(upload_to='gcash_receipts/', null=True, blank=True)
    # CASH PAYMENT TRACKING - NEW FIELDS
    cash_received = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Amount of cash received from customer"
    )
    change = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Change returned to customer"
    )

    def generate_order_id(self):
        today = timezone.now().strftime('%Y%m%d')
        prefix = 'KIO' if self.order_type == 'kiosk' else 'STA'
        
        last_order = Order.objects.filter(order_id__startswith=f"{prefix}-{today}-").order_by('-order_id').first()
        
        if last_order:
            try:
                last_sequence = int(last_order.order_id.split('-')[-1])
                new_sequence = last_sequence + 1
            except (ValueError, IndexError):
                new_sequence = 1
        else:
            new_sequence = 1
        
        return f"{prefix}-{today}-{new_sequence:03d}"

    def generate_hex_id(self):
        """Generate a unique 8-character hexadecimal ID"""
        while True:
            hex_id = uuid.uuid4().hex[:8].upper()
            if not Order.objects.filter(hex_id=hex_id).exists():
                return hex_id

    def save(self, *args, **kwargs):
        # Generate order_id if not set
        if not self.order_id:
            self.order_id = self.generate_order_id()
        
        # Generate hex_id if not set
        if not self.hex_id:
            self.hex_id = self.generate_hex_id()
        
        # Auto-calculate change if cash_received is provided
        if self.cash_received is not None and self.total_amount is not None:
            self.change = max(Decimal('0.00'), self.cash_received - self.total_amount)
        
        # Handle status changes - FIXED LOGIC
        if self.status == 'completed':
            if not self.completed_at:
                self.completed_at = timezone.now()
                self.is_paid = True
            if not self.paid_at:
                self.paid_at = timezone.now()
        
        # Ensure paid_at is set when is_paid is True
        if self.is_paid and not self.paid_at:
            self.paid_at = timezone.now()
        
        # Set customer details if customer exists
        if self.customer and not self.customer_name:
            self.customer_name = self.customer.name
        
        if self.customer and not self.customer_phone:
            self.customer_phone = self.customer.phone
        
        if self.is_daily_report and not self.report_date:
            self.report_date = timezone.now().date()
        
        super().save(*args, **kwargs)

    def __str__(self):
        customer_name = self.customer_name or (self.customer.name if self.customer else 'Walk-in')
        return f"{self.order_id} - {customer_name} - ₱{self.total_amount}"

    @property
    def display_id(self):
        """Return the hexadecimal ID for display purposes"""
        return f"#{self.hex_id}" if self.hex_id else f"#{self.id}"
    
    @property
    def requires_change_calculation(self):
        """Check if this order needs change calculation"""
        return self.payment_method == 'cash' and self.cash_received is not None
    
    @property
    def change_amount(self):
        """Calculate change amount"""
        if self.requires_change_calculation:
            return max(Decimal('0.00'), self.cash_received - self.total_amount)
        return Decimal('0.00')
    
    def can_void(self, user):
        """Check if user has permission to void this order"""
        # Admin/superusers can void any order
        if user.is_superuser:
            return True
        
        # Staff with admin role can void any order
        if hasattr(user, 'staff') and user.staff.role == 'admin':
            return True
        
        # Staff can void their own orders
        if user == self.staff:
            return True
        
        # Users with specific void permission
        if user.has_perm('cookie_app.void_any_order'):
            return True
        
        return False
    
    def void_order(self, voided_by, reason=""):
        """Void the order with permission checks"""
        if not self.can_void(voided_by):
            raise PermissionError("You don't have permission to void this order")
        
        if self.status == 'voided':
            raise ValueError("Order is already voided")
        
        self.status = 'voided'
        self.save()
        
        # Restore inventory
        self.restore_inventory()
        
        return True
    
    def restore_inventory(self):
        """Restore inventory when order is voided"""
        for item in self.items.all():
            cookie = item.cookie
            cookie.stock_quantity += item.quantity
            cookie.save()
    
    class Meta:
        permissions = [
            ("void_any_order", "Can void any order"),
            ("view_all_orders", "Can view all orders"),
        ]

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    cookie = models.ForeignKey(Cookie, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    
    @property
    def total_price(self):
        """Calculate total price for this order item"""
        return self.quantity * self.price
    
    def __str__(self):
        return f"{self.quantity}x {self.cookie.name} - ₱{self.price}"

class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('login', 'User Login'), ('logout', 'User Logout'), ('user_registered', 'User Registered'),
        ('order_created', 'Order Created'), ('order_updated', 'Order Updated'), ('order_completed', 'Order Completed'),
        ('order_voided', 'Order Voided'), ('cookie_added', 'Cookie Added'), ('cookie_updated', 'Cookie Updated'),
        ('cookie_deleted', 'Cookie Deleted'), ('inventory_updated', 'Inventory Updated'), ('staff_approved', 'Staff Approved'),
        ('staff_rejected', 'Staff Rejected'), ('staff_updated', 'Staff Updated'), ('staff_deactivated', 'Staff Deactivated'),
        ('staff_activated', 'Staff Activated'), ('staff_deleted', 'Staff Deleted'), ('daily_report_submitted', 'Daily Report Submitted'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    affected_model = models.CharField(max_length=50, blank=True, null=True)
    affected_id = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_action_display()} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ['-timestamp']

class VoidLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='void_logs')
    staff_member = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, related_name='voided_orders')
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_voids')
    void_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    original_total = models.DecimalField(max_digits=10, decimal_places=2)
    original_payment_method = models.CharField(max_length=20)
    void_id = models.CharField(max_length=20, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.void_id:
            self.void_id = f"VOID{str(uuid.uuid4())[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Void {self.void_id} - Order #{self.order.order_id}"

    class Meta:
        ordering = ['-void_date']

class StoreSettings(models.Model):
    """Singleton-style model for store configuration"""
    store_name = models.CharField(max_length=150, default="Cookie Craze")
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    business_hours = models.CharField(max_length=200, blank=True, null=True, help_text="e.g. Mon-Sun, 9:00 AM - 9:00 PM")

    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Tax rate as a percentage (e.g. 12.00 for 12%)"
    )

    gcash_instructions = models.TextField(blank=True, null=True, help_text="Instructions shown to customers for GCash payments")
    gcash_account_name = models.CharField(max_length=100, blank=True, null=True)
    gcash_account_number = models.CharField(max_length=50, blank=True, null=True)

    theme_primary_color = models.CharField(max_length=7, default="#8B4513")
    theme_secondary_color = models.CharField(max_length=7, default="#D2691E")

    logo = models.ImageField(upload_to='store/', null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.store_name or "Store Settings"

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj

class CashFloat(models.Model):
    FLOAT_TYPES = [
        ('opening', 'Opening Float'),
        ('additional', 'Additional Change'),
        ('closing', 'Closing Balance'),
        ('adjustment', 'Cash Adjustment'),
    ]
    
    ADJUSTMENT_TYPES = [
        ('shortage', 'Shortage'),
        ('excess', 'Excess'),
        ('change_add', 'Change Added'),
        ('change_remove', 'Change Removed'),
    ]
    
    date = models.DateField(default=timezone.now)
    float_type = models.CharField(max_length=20, choices=FLOAT_TYPES)
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cash_floats')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        # REMOVE this line to allow multiple adjustments per day:
        # unique_together = ['date', 'float_type', 'adjustment_type']
    
    def __str__(self):
        if self.adjustment_type:
            return f"{self.get_float_type_display()} - {self.get_adjustment_type_display()} - {self.date} - ₱{self.amount}"
        return f"{self.get_float_type_display()} - {self.date} - ₱{self.amount}"
    
    @classmethod
    def get_todays_opening_float(cls):
        today = timezone.now().date()
        try:
            return cls.objects.get(date=today, float_type='opening')
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def get_todays_additional_change(cls):
        today = timezone.now().date()
        return cls.objects.filter(
            date=today, 
            float_type__in=['additional', 'adjustment'],
            adjustment_type__in=['change_add', None]  # Include both additional and adjustment changes
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    @classmethod
    def get_todays_adjustments(cls):
        today = timezone.now().date()
        adjustments = cls.objects.filter(
            date=today, 
            float_type='adjustment'
        )
        return adjustments
    
    @classmethod
    def get_todays_total_adjustments(cls):
        today = timezone.now().date()
        result = cls.objects.filter(
            date=today, 
            float_type='adjustment'
        ).aggregate(
            total_shortage=Sum('amount', filter=Q(adjustment_type='shortage')),
            total_excess=Sum('amount', filter=Q(adjustment_type='excess')),
            total_change_add=Sum('amount', filter=Q(adjustment_type='change_add')),
            total_change_remove=Sum('amount', filter=Q(adjustment_type='change_remove'))
        )
        
        # Calculate net adjustment
        shortages = result['total_shortage'] or Decimal('0.00')
        excesses = result['total_excess'] or Decimal('0.00')
        change_added = result['total_change_add'] or Decimal('0.00')
        change_removed = result['total_change_remove'] or Decimal('0.00')
        
        return {
            'shortages': shortages,
            'excesses': excesses,
            'change_added': change_added,
            'change_removed': change_removed,
            'net_adjustment': (excesses + change_added) - (shortages + change_removed)
        }
    
    @classmethod
    def get_todays_total_float(cls):
        opening = cls.get_todays_opening_float()
        additional_change = cls.get_todays_additional_change()
        
        opening_amount = opening.amount if opening else Decimal('0.00')
        return opening_amount + additional_change