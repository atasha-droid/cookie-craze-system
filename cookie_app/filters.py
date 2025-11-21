# cookie_app/filters.py
import django_filters
from django import forms
from django.db import models
from .models import Order

class OrderFilter(django_filters.FilterSet):
    # Search filter for order_id and customer_name
    search = django_filters.CharFilter(
        method='filter_search',
        label='Search Orders',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by order ID, customer name...'
        })
    )
    
    # Status filter
    status = django_filters.ChoiceFilter(
        choices=Order.STATUS_CHOICES,
        label='Status',
        empty_label='All Statuses',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Order type filter
    order_type = django_filters.ChoiceFilter(
        choices=Order.ORDER_TYPES,
        label='Order Type',
        empty_label='All Types',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Payment method filter
    payment_method = django_filters.ChoiceFilter(
        choices=Order.PAYMENT_METHODS,
        label='Payment Method',
        empty_label='All Methods',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def filter_search(self, queryset, name, value):
        """Custom search method to search in multiple fields"""
        if value:
            return queryset.filter(
                models.Q(order_id__icontains=value) |
                models.Q(customer_name__icontains=value) |
                models.Q(hex_id__icontains=value)
            )
        return queryset

    class Meta:
        model = Order
        fields = ['search', 'status', 'order_type', 'payment_method']