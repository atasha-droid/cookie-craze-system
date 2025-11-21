# Generated migration for email verification fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cookie_app', '0014_remove_customer_ftue_completed'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='is_email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='customer',
            name='email_verification_token',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='customer',
            name='email_verification_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='customer',
            name='email_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
