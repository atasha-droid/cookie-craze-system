# cookie_app/apps.py
from django.apps import AppConfig

class CookieAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cookie_app'
    
    def ready(self):
        """
        Import signals when the app is ready
        This method is called when Django starts
        """
        try:
            import cookie_app.signals  # Import signals
            print("[OK] Signals imported successfully")
        except ImportError as e:
            print(f"[WARNING] Could not import signals: {e}")
        except Exception as e:
            print(f"[WARNING] Error importing signals: {e}")