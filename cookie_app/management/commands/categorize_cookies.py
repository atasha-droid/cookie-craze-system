from django.core.management.base import BaseCommand
from cookie_app.models import Cookie, Category

class Command(BaseCommand):
    help = 'Categorize all cookies based on their names and descriptions'

    def handle(self, *args, **options):
        # Ensure we have all necessary categories
        categories_data = [
            {'name': 'Classic', 'color': '#007bff', 'icon': 'fas fa-star', 'keywords': ['chocolate', 'vanilla', 'oatmeal', 'butter', 'peanut']},
            {'name': 'Premium', 'color': '#ffc107', 'icon': 'fas fa-crown', 'keywords': ['premium', 'gourmet', 'artisan', 'hazelnut', 'pistachio', 'almond', 'matcha', 'ube']},
            {'name': 'Seasonal', 'color': '#28a745', 'icon': 'fas fa-calendar-alt', 'keywords': ['seasonal', 'holiday', 'christmas', 'valentine', 'easter', 'halloween']},
            {'name': 'Specialty', 'color': '#6c757d', 'icon': 'fas fa-gem', 'keywords': ['specialty', 'unique', 'cream cheese', 'mint', 'caramel', 'spice']},
        ]
        
        categories = {}
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={
                    'color': cat_data['color'],
                    'icon': cat_data['icon'],
                    'description': f'{cat_data["name"]} cookies collection'
                }
            )
            categories[cat_data['name']] = {
                'obj': category,
                'keywords': cat_data['keywords']
            }
            if created:
                self.stdout.write(f"Created category: {category.name}")
            else:
                self.stdout.write(f"Found existing category: {category.name}")

        # Categorize all cookies
        categorized_count = 0
        uncategorized_cookies = []
        
        for cookie in Cookie.objects.all():
            assigned_category = None
            
            # Try to categorize based on name and description
            search_text = f"{cookie.name} {cookie.description or ''}".lower()
            
            # Check each category's keywords
            for cat_name, cat_info in categories.items():
                for keyword in cat_info['keywords']:
                    if keyword.lower() in search_text:
                        assigned_category = cat_info['obj']
                        break
                if assigned_category:
                    break
            
            # If no category found, assign to Classic as default
            if not assigned_category:
                assigned_category = categories['Classic']['obj']
                uncategorized_cookies.append(cookie.name)
            
            # Update the cookie's category
            if cookie.category != assigned_category:
                cookie.category = assigned_category
                cookie.save()
                categorized_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully categorized {categorized_count} cookies!"
            )
        )
        
        if uncategorized_cookies:
            self.stdout.write(
                f"Assigned {len(uncategorized_cookies)} cookies to Classic category (default):"
            )
            for cookie_name in uncategorized_cookies[:10]:  # Show first 10
                self.stdout.write(f"  - {cookie_name}")
            if len(uncategorized_cookies) > 10:
                self.stdout.write(f"  ... and {len(uncategorized_cookies) - 10} more")

        # Final summary
        self.stdout.write("\n=== FINAL CATEGORY SUMMARY ===")
        for cat_name, cat_info in categories.items():
            count = cat_info['obj'].cookies.count()
            self.stdout.write(f"{cat_name}: {count} cookies")