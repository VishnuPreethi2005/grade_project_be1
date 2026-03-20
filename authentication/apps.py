from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """
    Configuration class for the 'authentication' app.

    This class defines the configuration for the 'authentication' app, including the default
    auto-generated primary key field and the name of the app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"

    def ready(self):
        """Import signals when app is ready"""
        import authentication.signals  # noqa
