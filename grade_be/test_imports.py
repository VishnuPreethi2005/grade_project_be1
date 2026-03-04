
import sys
import os

def test_import(module_name):
    print(f"Attempting to import {module_name}...", end=" ", flush=True)
    try:
        __import__(module_name)
        print("OK")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

print(f"Python version: {sys.version}")
print(f"CWD: {os.getcwd()}")
print("-" * 30)

# Import basic stuff first
test_import("django")
test_import("fastapi")
test_import("uvicorn")
test_import("PIL")
test_import("fitz")
test_import("cv2")
test_import("numpy")

print("-" * 30)
print("Testing heavy native libraries...")
test_import("ultralytics")

print("-" * 30)
print("Testing Django Setup...")
try:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "promptRightProd.settings")
    import django
    django.setup()
    print("django.setup() OK")
except Exception as e:
    print(f"django.setup() CRASHED: {e}")

print("-" * 30)
print("Testing Application Imports...")
test_import("workspace_module1.main")
test_import("workspace_module2.main")

print("-" * 30)
print("Diagnostic Complete.")
