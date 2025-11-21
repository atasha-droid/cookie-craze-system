from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from cookie_app.models import Cookie, Sale, Customer

class Command(BaseCommand):
    help = 'Sets up user groups and permissions for the cookie system'
    
    def handle(self, *args, **options):
        # Create groups
        admin_group, created = Group.objects.get_or_create(name='Admin')
        staff_group, created = Group.objects.get_or_create(name='Staff')
        
        # Get content types
        cookie_content_type = ContentType.objects.get_for_model(Cookie)
        sale_content_type = ContentType.objects.get_for_model(Sale)
        customer_content_type = ContentType.objects.get_for_model(Customer)
        
        
        # Get all permissions
        all_permissions = Permission.objects.all()
        
        # Staff permissions - limited access
        staff_permissions = [
            Permission.objects.get(codename='view_cookie', content_type=cookie_content_type),
            Permission.objects.get(codename='change_cookie', content_type=cookie_content_type),
            Permission.objects.get(codename='view_sale', content_type=sale_content_type),
            Permission.objects.get(codename='add_sale', content_type=sale_content_type),
            Permission.objects.get(codename='change_sale', content_type=sale_content_type),
            Permission.objects.get(codename='view_customer', content_type=customer_content_type),
            Permission.objects.get(codename='add_customer', content_type=customer_content_type),
        ]
        
        # Assign permissions to groups
        for perm in all_permissions:
            admin_group.permissions.add(perm)
        
        for perm in staff_permissions:
            staff_group.permissions.add(perm)
        
        self.stdout.write(
            self.style.SUCCESS('Successfully set up user groups and permissions!')
        )