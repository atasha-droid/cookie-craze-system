from django.core.management.base import BaseCommand
from cookie_app.models import Cookie, Category

class Command(BaseCommand):
    help = 'Assign default categories to uncategorized cookies'

    def handle(self, *args, **options):
        # Get or create default categories
        categories_data = [
            {'name': 'Classic', 'color': '#007bff', 'icon': 'fas fa-star'},
            {'name': 'Premium', 'color': '#ffc107', 'icon': 'fas fa-crown'},
            {'name': 'Seasonal', 'color': '#28a745', 'icon': 'fas fa-calendar-alt'},
            {'name': 'Specialty', 'color': '#6c757d', 'icon': 'fas fa-gem'},
        ]
        
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults=cat_data
            )
            if created:
                self.stdout.write(f"Created category: {category.name}")
        
        # Assign classic category to all uncategorized cookies
        classic_category = Category.objects.get(name='Classic')
        uncategorized_count = Cookie.objects.filter(category__isnull=True).count()
        
        if uncategorized_count > 0:
            Cookie.objects.filter(category__isnull=True).update(category=classic_category)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Assigned {uncategorized_count} cookies to {classic_category.name} category"
                )
            )
        else:
            self.stdout.write("No uncategorized cookies found.")