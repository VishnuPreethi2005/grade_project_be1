"""
mini_ide_server_std.py
======================
Crash-proof Mini IDE backend.
Uses ONLY Python built-ins that are safe under -S (skip site-packages):
  http.server, socketserver, json, os, subprocess, shutil, socket, time
No logging, no urllib — avoids Access Violations on Windows.
"""
import http.server
import socketserver
import json
import os
import subprocess
import shutil
import socket
import time
from urllib.parse import urlparse, parse_qs

PORT = 8000
WORKSPACE_ROOT = os.getcwd()
CURRENT_DIR = None
DOCKER_HOST_ROOT = r"C:\ip_docker"
STATIC_DIR = os.path.join(WORKSPACE_ROOT, "workspace_module1", "static")
GEMINI_API_KEY = "AIzaSyDVVGJ6jQb_kuhlnKRgif9xO8p4wf3jk1w"


class MiniIDEHandler(http.server.BaseHTTPRequestHandler):

    # Silence access log spam
    def log_message(self, fmt, *args): pass

    # ── GET ────────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        url_path = parsed.path
        query = parse_qs(parsed.query)

        if url_path == "/mini_ide":
            self.serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html")

        elif url_path == "/list_files":
            if not CURRENT_DIR:
                self.send_json({"files": [], "current_dir": None, "status": "no_workspace"})
            else:
                self.send_json({"files": self._tree(CURRENT_DIR), "current_dir": CURRENT_DIR, "status": "success"})

        elif url_path == "/view_file":
            fname = query.get("file_name", [None])[0]
            if fname:
                self.serve_file(os.path.join(CURRENT_DIR or WORKSPACE_ROOT, fname), "text/plain")
            else:
                self.send_error(400)

        elif url_path == "/get_host_root":
            self.send_json({"host_root": DOCKER_HOST_ROOT})

        elif url_path == "/pick_folder":
            self._pick_folder()

        elif url_path == "/pick_host_root":
            self._pick_host_root()

        else:
            local = os.path.join(STATIC_DIR, url_path.lstrip("/"))
            if os.path.isfile(local):
                self.serve_file(local)
            else:
                self.send_error(404, "Not Found")

    # ── POST ───────────────────────────────────────────────────────────────
    def do_POST(self):
        global CURRENT_DIR, DOCKER_HOST_ROOT
        url_path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            data = {}

        if url_path == "/save_file":
            fname = data.get("file_name")
            content = data.get("code_content", "")
            if fname and CURRENT_DIR:
                path = os.path.join(CURRENT_DIR, fname)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.send_json({"status": "success", "saved_to": path})
            else:
                self.send_error(400)

        elif url_path == "/save_as":
            content = data.get("code_content", "")
            initial_dir = CURRENT_DIR or os.path.expanduser("~")
            initial_file = data.get("file_name", "untitled.py")
            # Use tkinter Save As dialog
            saved_path = self._save_dialog(initial_dir, initial_file)
            if saved_path:
                os.makedirs(os.path.dirname(os.path.abspath(saved_path)), exist_ok=True)
                with open(saved_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.send_json({"status": "success", "saved_to": saved_path, "file_name": os.path.basename(saved_path)})
            else:
                self.send_json({"status": "cancelled"})

        elif url_path == "/run_file":
            fname = data.get("file_name")
            stdin = data.get("stdin_input", "")
            if fname and CURRENT_DIR:
                path = os.path.join(CURRENT_DIR, fname)
                res = subprocess.run(
                    [os.sys.executable, path],
                    input=stdin, capture_output=True, text=True, timeout=30, cwd=CURRENT_DIR
                )
                self.send_json({"stdout": res.stdout, "stderr": res.stderr, "status": "success"})
            else:
                self.send_error(400)

        elif url_path == "/create_folder_workspace":
            name = data.get("name", "NewProject")
            path = data.get("path") or os.path.join(DOCKER_HOST_ROOT, name)
            os.makedirs(path, exist_ok=True)
            CURRENT_DIR = path
            self.send_json({"current_dir": CURRENT_DIR, "status": "success"})

        elif url_path == "/close_workspace":
            to_del = CURRENT_DIR
            CURRENT_DIR = None
            if to_del:
                self._cleanup(to_del)
            self.send_json({"status": "success"})

        elif url_path == "/create_item":
            if not CURRENT_DIR:
                return self.send_error(400)
            name = data.get("name")
            itype = data.get("type")
            path = os.path.join(CURRENT_DIR, name)
            if itype == "folder":
                os.makedirs(path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
            self.send_json({"status": "success"})

        elif url_path == "/delete_item":
            if not CURRENT_DIR:
                return self.send_error(400)
            target = data.get("path") or data.get("name")
            path = os.path.join(CURRENT_DIR, target)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self.send_json({"status": "success"})

        elif url_path == "/ai_complete":
            prefix = data.get("prefix", "")
            suffix = data.get("suffix", "")
            fname = data.get("filename", "script.py")
            suggestions = self._gemini_complete(prefix, suffix, fname)
            self.send_json({"suggestions": suggestions, "status": "success"})

        else:
            self.send_error(404)

    # ── Gemini via raw socket (no urllib, no requests) ─────────────────────
    def _gemini_complete(self, prefix, suffix, filename):
        if not GEMINI_API_KEY:
            return []
        prompt = (
            f"Act as a Python code completion expert for {filename}.\n"
            f"Provide ONLY the most likely next line of code. No markdown, no explanation.\n\n"
            f"Code before cursor:\n{prefix}\n\nCode after cursor:\n{suffix}\n\nCompletion:"
        )
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        host = "generativelanguage.googleapis.com"
        path = f"/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        request = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8") + payload

        try:
            import ssl
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=6) as raw_sock:
                with ctx.wrap_socket(raw_sock, server_hostname=host) as s:
                    s.sendall(request)
                    response = b""
                    while True:
                        chunk = s.recv(4096)
                        if not chunk:
                            break
                        response += chunk
            # Split HTTP headers from body
            body = response.split(b"\r\n\r\n", 1)[-1]
            # Handle chunked transfer encoding
            if b"\r\n" in body[:8]:  # chunked
                try:
                    parts = []
                    while body:
                        line_end = body.index(b"\r\n")
                        size = int(body[:line_end], 16)
                        if size == 0:
                            break
                        parts.append(body[line_end + 2: line_end + 2 + size])
                        body = body[line_end + 2 + size + 2:]
                    body = b"".join(parts)
                except Exception:
                    pass
            result = json.loads(body.decode("utf-8"))
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return [text.strip().strip("`")]
        except Exception:
            return []

    # ── Folder dialog via tkinter (deferred import) ────────────────────────
    def _pick_folder(self):
        global CURRENT_DIR
        path = self._dialog("Select Folder to Open")
        if path:
            path = os.path.abspath(path)
            if not path.lower().startswith(DOCKER_HOST_ROOT.lower()):
                os.makedirs(DOCKER_HOST_ROOT, exist_ok=True)
                target = os.path.join(DOCKER_HOST_ROOT, os.path.basename(path))
                if os.path.exists(target):
                    try:
                        shutil.rmtree(target)
                    except Exception:
                        pass
                shutil.copytree(path, target)
                path = target
            CURRENT_DIR = path
            self.send_json({"current_dir": CURRENT_DIR, "status": "success"})
        else:
            self.send_json({"status": "cancelled"})

    def _pick_host_root(self):
        global DOCKER_HOST_ROOT
        path = self._dialog("Select Docker Host Root")
        if path:
            DOCKER_HOST_ROOT = os.path.abspath(path)
            self.send_json({"host_root": DOCKER_HOST_ROOT, "status": "success"})
        else:
            self.send_json({"status": "cancelled"})

    def _save_dialog(self, initial_dir, initial_file):
        """Open a native Save As dialog and return the chosen path, or None."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            ext = os.path.splitext(initial_file)[1] or ".py"
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            result = filedialog.asksaveasfilename(
                title="Save As",
                initialdir=initial_dir,
                initialfile=initial_file,
                defaultextension=ext,
                filetypes=[
                    ("Python files", "*.py"),
                    ("JavaScript files", "*.js"),
                    ("HTML files", "*.html"),
                    ("Text files", "*.txt"),
                    ("All files", "*.*")
                ]
            )
            root.destroy()
            return result if result else None
        except Exception:
            return None

    def _dialog(self, title):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            result = filedialog.askdirectory(title=title)
            root.destroy()
            return result
        except Exception:
            return None

    def _cleanup(self, path):
        try:
            n_curr = os.path.normpath(path).lower()
            n_root = os.path.normpath(DOCKER_HOST_ROOT).lower()
            if n_curr.startswith(n_root) and len(n_curr) > len(n_root):
                for _ in range(3):
                    try:
                        shutil.rmtree(path)
                        break
                    except Exception:
                        time.sleep(0.4)
        except Exception:
            pass

    def _tree(self, base_path):
        nodes = []
        try:
            items = sorted(
                os.listdir(base_path),
                key=lambda x: (not os.path.isdir(os.path.join(base_path, x)), x.lower())
            )
            for item in items:
                if item.startswith(".") or item in ("__pycache__", "venv", "node_modules", "myenv", "venv_broken", "venv_new"):
                    continue
                full = os.path.join(base_path, item)
                rel = os.path.relpath(full, CURRENT_DIR).replace("\\", "/")
                is_dir = os.path.isdir(full)
                node = {"name": item, "path": rel, "type": "folder" if is_dir else "file"}
                if is_dir:
                    node["children"] = self._tree(full)
                nodes.append(node)
        except Exception:
            pass
        return nodes

    # ── Helpers ───────────────────────────────────────────────────────────
    def serve_file(self, path, content_type=None):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            if content_type:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(404)

    def send_json(self, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), MiniIDEHandler) as httpd:
        httpd.serve_forever()
