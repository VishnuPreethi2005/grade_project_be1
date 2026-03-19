"""
WSGI config for promptRightProd project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

settings_module = (
    "promptRightProd.deployment_settings"
    if "WEBSITE_SITE_NAME" in os.environ
    else "promptRightProd.settings"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)


application = get_wsgi_application()
