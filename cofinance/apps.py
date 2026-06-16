from django.apps import AppConfig

class CofinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cofinance'

    def ready(self):
        try:
            import cofinance.signals
        except ImportError:
            pass
