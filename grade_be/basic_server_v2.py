
import http.server
import socketserver

PORT = 8005
class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Hello! System Server is UP on 8005.")

with socketserver.TCPServer(("127.0.0.1", PORT), MyHandler) as httpd:
    print("serving at port", PORT)
    httpd.serve_forever()
