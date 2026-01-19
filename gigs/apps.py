from django.apps import AppConfig

class GigsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'gigs'

    def ready(self):
        # This ensures signals.py is imported when Django starts
        import gigs.signals  # noqa