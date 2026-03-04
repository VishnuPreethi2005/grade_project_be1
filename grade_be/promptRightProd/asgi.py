"""
ASGI config for promptRightProd project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

settings_module = (
    "promptRightProd.deployment_settings"
    if "WEBSITE_SITE_NAME" in os.environ
    else "promptRightProd.settings"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

django_application = get_asgi_application()

from workspace_module1.main import app as fastapi_app
from workspace_module2.main import app as module2_app

async def application(scope, receive, send):
    if scope["type"] == "http":
        path = scope["path"]
        if path.startswith("/module2"):
            await module2_app(scope, receive, send)
            return
        
        module1_paths = ["/pick_folder", "/create_folder_workspace", "/create_item", "/save_file", 
                        "/view_file", "/run_file", "/mini_ide", "/list_files", "/delete_item",
                        "/close_workspace", "/get_host_root", "/update_host_root", "/pick_host_root"]
        
        if path in module1_paths or path.startswith("/docs") or path.startswith("/openapi.json"):
            await fastapi_app(scope, receive, send)
            return
    await django_application(scope, receive, send)
