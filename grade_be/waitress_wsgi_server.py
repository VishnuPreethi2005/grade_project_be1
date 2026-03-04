
from waitress import serve
from a2wsgi import ASGIMiddleware
from stable_ide_server import app as fast_app

# Wrap FastAPI ASGI app with a WSGI bridge
# This sometimes bypasses uvicorn's event loop issues on unstable Windows environments
wsgi_app = ASGIMiddleware(fast_app)

if __name__ == "__main__":
    print("--------------------------------------------------")
    print("🚀 Mini IDE (Waitress WSGI mode) starting...")
    print("🔗 Link: http://localhost:8000/mini_ide")
    print("--------------------------------------------------")
    serve(wsgi_app, host='127.0.0.1', port=8000, threads=8)
