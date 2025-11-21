# cookie_app/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from django.contrib.auth.models import User
from allauth.socialaccount.signals import pre_social_login
from .models import Order, UserProfile, Customer
from .utils import log_activity

@receiver(post_save, sender=Order)
def notify_new_order(sender, instance, created, **kwargs):
    """
    Signal to handle new order creation and send real-time notifications
    """
    if created:
        try:
            # Increment new orders count for real-time notifications
            cache_key = 'new_orders_count'
            current_count = cache.get(cache_key, 0)
            cache.set(cache_key, current_count + 1, 300)  # 5 minutes timeout
            
            # Log the activity
            log_activity(
                user=None,  # System generated
                action='order_created',
                description=f'New order received: {instance.hex_id} - {instance.customer_name}',
                affected_model='Order',
                affected_id=instance.id
            )
            
            print(f"[ORDER] New order signal triggered: {instance.hex_id}")  # Debug print
            
        except Exception as e:
            print(f"Error in order signal: {e}")

@receiver(pre_social_login)
def handle_google_login(sender, request, sociallogin, **kwargs):
    """
    Signal to observe Google OAuth login.
    NOTE: Profile creation is handled by CustomSocialAccountAdapter.save_user.
    """
    try:
        user = sociallogin.user
        print(f"Google login signal triggered for: {user.email}")
        # Do NOT create UserProfile/Customer here anymore.
    except Exception as e:
        print(f"Error in Google login signal: {e}")
            