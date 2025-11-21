from django.core.management.base import BaseCommand
from cookie_app.models import Cookie
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Create sample cookie data for all categories'

    def handle(self, *args, **kwargs):
        sample_cookies = [
            # CLASSIC COOKIES
            {
                'name': 'Chocolate Chip Classic',
                'flavor': 'chocolate_chip',
                'description': 'Classic buttery cookie loaded with semi-sweet chocolate chips',
                'price': 25.00,
                'stock_quantity': 50,
                'category': 'classic',
                'expiration_date': datetime.now() + timedelta(days=30)
            },
            {
                'name': 'Grandma\'s Sugar Cookie',
                'flavor': 'sugar',
                'description': 'Soft, buttery sugar cookies with crisp edges',
                'price': 20.00,
                'stock_quantity': 65,
                'category': 'classic',
                'expiration_date': datetime.now() + timedelta(days=25)
            },
            {
                'name': 'Oatmeal Raisin Delight',
                'flavor': 'oatmeal_raisin',
                'description': 'Hearty oatmeal cookies with plump raisins and cinnamon',
                'price': 22.00,
                'stock_quantity': 45,
                'category': 'classic',
                'expiration_date': datetime.now() + timedelta(days=28)
            },
            {
                'name': 'Peanut Butter Bliss',
                'flavor': 'peanut_butter',
                'description': 'Rich peanut butter cookies with criss-cross pattern',
                'price': 23.00,
                'stock_quantity': 55,
                'category': 'classic',
                'expiration_date': datetime.now() + timedelta(days=32)
            },
            {
                'name': 'Snickerdoodle Magic',
                'flavor': 'snickerdoodle',
                'description': 'Soft cookies rolled in cinnamon sugar with chewy centers',
                'price': 21.00,
                'stock_quantity': 60,
                'category': 'classic',
                'expiration_date': datetime.now() + timedelta(days=26)
            },

            # PREMIUM COOKIES
            {
                'name': 'White Chocolate Macadamia',
                'flavor': 'macadamia',
                'description': 'Buttery cookies with premium white chocolate and macadamia nuts',
                'price': 45.00,
                'stock_quantity': 30,
                'category': 'premium',
                'expiration_date': datetime.now() + timedelta(days=20)
            },
            {
                'name': 'Double Chocolate Dream',
                'flavor': 'double_chocolate',
                'description': 'Rich double chocolate cookies with dark chocolate chunks',
                'price': 42.00,
                'stock_quantity': 35,
                'category': 'premium',
                'expiration_date': datetime.now() + timedelta(days=22)
            },
            {
                'name': 'Red Velvet Supreme',
                'flavor': 'red_velvet',
                'description': 'Luxurious red velvet cookies with cream cheese flavor',
                'price': 48.00,
                'stock_quantity': 28,
                'category': 'premium',
                'expiration_date': datetime.now() + timedelta(days=18)
            },
            {
                'name': 'Funfetti Celebration',
                'flavor': 'funfetti',
                'description': 'Colorful vanilla cookies with rainbow sprinkles throughout',
                'price': 38.00,
                'stock_quantity': 40,
                'category': 'premium',
                'expiration_date': datetime.now() + timedelta(days=24)
            },

            # SEASONAL COOKIES
            {
                'name': 'Gingerbread Spice',
                'flavor': 'gingerbread',
                'description': 'Warm gingerbread cookies with holiday spices and molasses',
                'price': 32.00,
                'stock_quantity': 45,
                'category': 'seasonal',
                'expiration_date': datetime.now() + timedelta(days=15)
            },
            {
                'name': 'Pumpkin Spice Delight',
                'flavor': 'gingerbread',
                'description': 'Seasonal pumpkin cookies with warm autumn spices',
                'price': 35.00,
                'stock_quantity': 38,
                'category': 'seasonal',
                'expiration_date': datetime.now() + timedelta(days=12)
            },
            {
                'name': 'Peppermint Bark Cookie',
                'flavor': 'chocolate_chip',
                'description': 'Chocolate cookies with crushed peppermint candy pieces',
                'price': 36.00,
                'stock_quantity': 42,
                'category': 'seasonal',
                'expiration_date': datetime.now() + timedelta(days=10)
            },

            # CUSTOM ORDERS
            {
                'name': 'Custom Birthday Cookie',
                'flavor': 'sugar',
                'description': 'Customizable sugar cookies for birthday celebrations',
                'price': 50.00,
                'stock_quantity': 10,
                'category': 'custom',
                'expiration_date': datetime.now() + timedelta(days=7)
            },
            {
                'name': 'Wedding Favor Cookie',
                'flavor': 'vanilla',
                'description': 'Elegant cookies perfect for wedding favors and events',
                'price': 55.00,
                'stock_quantity': 8,
                'category': 'custom',
                'expiration_date': datetime.now() + timedelta(days=5)
            },
        ]

        created_count = 0
        for cookie_data in sample_cookies:
            cookie, created = Cookie.objects.get_or_create(
                name=cookie_data['name'],
                defaults=cookie_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created: {cookie.name} ({cookie.get_category_display()})')
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully created {created_count} sample cookies across 4 categories')
        )