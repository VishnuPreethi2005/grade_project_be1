
from waitress import serve
def app(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [b"Hello from Waitress!"]

if __name__ == "__main__":
    print("Serving on port 8000...")
    serve(app, host='127.0.0.1', port=8000)
