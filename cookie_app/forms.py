from django import forms
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Cookie, Customer, Order, UserProfile, Category, Staff, StoreSettings
import secrets

class CustomerOrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={
                'class': 'unified-form-control',
                'rows': 3,
                'placeholder': 'Any special instructions for your order...'
            }),
        }

class DailySalesForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date', 
            'class': 'unified-form-control',
            'readonly': 'readonly'
        }),
        label="Report Date",
        initial=timezone.now().date
    )
    
    payment_method = forms.ChoiceField(
        choices=Order.PAYMENT_METHODS,
        widget=forms.Select(attrs={'class': 'unified-form-control'}),
        initial='gcash'
    )

class CustomerRegistrationForm(UserCreationForm):
    name = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'unified-form-control'}))
    phone = forms.CharField(max_length=20, required=True, widget=forms.TextInput(attrs={'class': 'unified-form-control'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'unified-form-control'}))
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'name', 'phone']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'password1': forms.PasswordInput(attrs={'class': 'unified-form-control'}),
            'password2': forms.PasswordInput(attrs={'class': 'unified-form-control'}),
        }
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_active = False  # Deactivate until email is verified
        if commit:
            user.save()
            # Create UserProfile first
            user_profile = UserProfile.objects.create(
                user=user,
                user_type='customer'
            )
            # Generate verification token
            verification_token = secrets.token_urlsafe(48)
            
            # Then create Customer linked to UserProfile with verification token
            Customer.objects.create(
                user_profile=user_profile,
                name=self.cleaned_data['name'],
                phone=self.cleaned_data['phone'],
                email=self.cleaned_data['email'],
                is_email_verified=False,
                email_verification_token=verification_token,
                email_verification_sent_at=timezone.now()
            )
        return user

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'phone': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'email': forms.EmailInput(attrs={'class': 'unified-form-control'}),
        }

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'color', 'icon', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'description': forms.Textarea(attrs={'class': 'unified-form-control', 'rows': 3}),
            'color': forms.TextInput(attrs={'class': 'unified-form-control', 'type': 'color'}),
            'icon': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Category Name',
            'description': 'Description',
            'color': 'Color',
            'icon': 'Icon Class',
            'is_active': 'Active',
        }
    
    def clean_name(self):
        name = self.cleaned_data['name']
        if Category.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('A category with this name already exists.')
        return name

class CookieForm(forms.ModelForm):
    class Meta:
        model = Cookie
        fields = ['name', 'flavor', 'category', 'price', 'stock_quantity', 'description', 'expiration_date', 'is_available']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'flavor': forms.Select(attrs={'class': 'unified-form-control'}),
            'category': forms.Select(attrs={'class': 'unified-form-control'}),
            'price': forms.NumberInput(attrs={'class': 'unified-form-control', 'step': '0.01', 'min': '0.01'}),
            'stock_quantity': forms.NumberInput(attrs={'class': 'unified-form-control', 'min': '0'}),
            'description': forms.Textarea(attrs={'class': 'unified-form-control', 'rows': 3}),
            'expiration_date': forms.DateInput(attrs={'class': 'unified-form-control', 'type': 'date'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Cookie Name',
            'flavor': 'Flavor',
            'category': 'Category',
            'price': 'Price (₱)',
            'stock_quantity': 'Stock Quantity',
            'description': 'Description',
            'expiration_date': 'Expiration Date',
            'is_available': 'Available for Sale',
        }

class SaleForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['customer', 'payment_method']
        widgets = {
            'customer': forms.Select(attrs={'class': 'unified-form-control'}),
            'payment_method': forms.Select(attrs={'class': 'unified-form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].required = False

class StaffRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'unified-form-control'}))
    phone_number = forms.CharField(max_length=20, required=True, widget=forms.TextInput(attrs={'class': 'unified-form-control'}))
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'phone_number']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'password1': forms.PasswordInput(attrs={'class': 'unified-form-control'}),
            'password2': forms.PasswordInput(attrs={'class': 'unified-form-control'}),
        }
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_active = False  # Staff accounts need approval
        if commit:
            user.save()
            # Create Staff profile
            Staff.objects.create(
                user=user,
                phone_number=self.cleaned_data['phone_number'],
                role='pending',
                is_active=False
            )
        return user

class StaffEditForm(forms.ModelForm):
    username = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'unified-form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'unified-form-control'}))
    
    class Meta:
        model = Staff
        fields = ['username', 'email', 'role', 'phone_number', 'is_active']
        widgets = {
            'role': forms.Select(attrs={'class': 'unified-form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['username'].initial = self.instance.user.username
            self.fields['email'].initial = self.instance.user.email
    
    def save(self, commit=True):
        staff = super().save(commit=False)
        if commit:
            # Update user information
            staff.user.username = self.cleaned_data['username']
            staff.user.email = self.cleaned_data['email']
            staff.user.save()
            staff.save()
        return staff

class WalkInOrderForm(forms.Form):
    customer_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'unified-form-control',
            'placeholder': 'Enter customer name'
        })
    )
    customer_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'unified-form-control',
            'placeholder': 'Phone number (optional)'
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'unified-form-control',
            'rows': 3,
            'placeholder': 'Special instructions or notes...'
        }),
        label='Order Notes'
    )


class StoreSettingsForm(forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = [
            'store_name', 'contact_email', 'contact_phone', 'address',
            'business_hours', 'tax_rate',
            'gcash_account_name', 'gcash_account_number', 'gcash_instructions',
            'theme_primary_color', 'theme_secondary_color', 'logo',
        ]
        widgets = {
            'store_name': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'unified-form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'address': forms.Textarea(attrs={'class': 'unified-form-control', 'rows': 2}),
            'business_hours': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'unified-form-control', 'step': '0.01', 'min': '0'}),
            'gcash_account_name': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'gcash_account_number': forms.TextInput(attrs={'class': 'unified-form-control'}),
            'gcash_instructions': forms.Textarea(attrs={'class': 'unified-form-control', 'rows': 3}),
            'theme_primary_color': forms.TextInput(attrs={'class': 'unified-form-control', 'type': 'color'}),
            'theme_secondary_color': forms.TextInput(attrs={'class': 'unified-form-control', 'type': 'color'}),
        }

class StaffSaleForm(forms.Form):
    customer_id = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'unified-form-control',
            'placeholder': 'Search customer by name or ID...'
        })
    )
    customer_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'unified-form-control',
            'placeholder': 'Or enter customer name manually'
        })
    )
    customer_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'unified-form-control',
            'placeholder': 'Customer phone (optional)'
        })
    )
    payment_method = forms.ChoiceField(
        choices=Order.PAYMENT_METHODS,
        widget=forms.Select(attrs={'class': 'unified-form-control'}),
        initial='gcash'
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'unified-form-control',
            'rows': 3,
            'placeholder': 'Special instructions or notes...'
        }),
        label='Order Notes'
    )