# cookie_app/adapters.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import perform_login
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.models import User
from .models import UserProfile, Customer, Staff
import logging

logger = logging.getLogger(__name__)

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for social account authentication.
    CRITICAL: Ensures ALL social logins (Google, etc.) create CUSTOMER accounts ONLY.
    Staff cannot use social login - they must use traditional username/password.
    """
    
    def pre_social_login(self, request, sociallogin):
        """Custom logic before social login"""
        user = sociallogin.user
        print(f"[SOCIAL LOGIN] Pre-login for: {user.email}")
        
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        
        extra_data = sociallogin.account.extra_data
        name = extra_data.get('name') or (
            f"{extra_data.get('given_name', '')} {extra_data.get('family_name', '')}".strip()
        ) or user.email.split('@')[0]

        # Clean up any staff profile if it exists
        self.cleanup_staff_profile(user)

        # Get or create user profile, forcing user_type to 'customer'
        user_profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={'user_type': 'customer'}
        )
        if user_profile.user_type != 'customer':
            user_profile.user_type = 'customer'
            user_profile.save()

        # Get or create customer with ftue_completed=False by default
        Customer.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                'name': name,
                'email': user.email or '',
                'ftue_completed': False
            }
        )
        
        return user

    def cleanup_staff_profile(self, user):
        """Remove any staff profile for social login users"""
        try:
            if hasattr(user, 'staff'):
                logger.info(f"[SOCIAL LOGIN] Removing staff profile for social login user: {user.email}")
                print(f"[SOCIAL LOGIN] Removing staff profile for: {user.email}")
                user.staff.delete()
        except Exception as e:
            logger.error(f"[SOCIAL LOGIN] Error cleaning up staff profile: {e}")

    def ensure_customer_profile(self, user):
        """Ensure existing user has customer profile (not staff)"""
        # Get or create user profile
        user_profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={'user_type': 'customer'}
        )
        
        # Force customer type for social logins
        if user_profile.user_type != 'customer':
            logger.info(f"[SOCIAL LOGIN] Changing existing user {user.email} from {user_profile.user_type} to customer")
            user_profile.user_type = 'customer'
            user_profile.save()
        
        # Remove staff profile if exists
        self.cleanup_staff_profile(user)
        
        # Ensure customer profile exists
        if not hasattr(user_profile, 'customer'):
            Customer.objects.create(
                user_profile=user_profile,
                name=user.get_full_name() or user.email.split('@')[0],
                email=user.email
            )