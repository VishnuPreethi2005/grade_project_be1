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

MODULE1_HTTP_PATHS = {
    "/attach_local_dataset",
    "/close_workspace",
    "/create_folder_workspace",
    "/create_item",
    "/delete_item",
    "/execute-command",
    "/file_preview",
    "/get_host_root",
    "/list_files",
    "/mini_ide",
    "/pick_folder",
    "/pick_host_root",
    "/rename_item",
    "/run_file",
    "/save_file",
    "/select_python_version",
    "/start-project",
    "/stop-project",
    "/terminal/set_container",
    "/update_host_root",
    "/view_file",
    "/zip_workspace",
}
MODULE1_WEBSOCKET_PATHS = {
    "/ws/lsp",
    "/ws/terminal",
}
MODULE2_HTTP_PREFIXES = ("/module2",)


def _is_module1_http_path(path: str) -> bool:
    return path in MODULE1_HTTP_PATHS


def _is_module1_websocket_path(path: str) -> bool:
    return path in MODULE1_WEBSOCKET_PATHS


def _is_module2_http_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in MODULE2_HTTP_PREFIXES)


async def application(scope, receive, send):
    path = scope.get("path", "")

    if scope["type"] == "websocket":
        if _is_module1_websocket_path(path):
            await fastapi_app(scope, receive, send)
            return

    if scope["type"] == "http":
        if _is_module2_http_path(path):
            await module2_app(scope, receive, send)
            return

        if _is_module1_http_path(path):
            await fastapi_app(scope, receive, send)
            return

    await django_application(scope, receive, send)
