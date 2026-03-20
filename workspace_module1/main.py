from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import signal
import select
import re
import platform
import importlib
from urllib.parse import parse_qs
from collections import deque
from typing import List, Optional, Dict, Any
from workspace_module2.container_manager import start_or_reuse_container
from workspace_module1.chatbot import run_chatbot_menu, ChatbotSession
# import tkinter as tk (Moved to local scope)
# from tkinter import filedialog (Moved to local scope)

app = FastAPI()

# Global state
CURRENT_DIR: Optional[str] = None
DOCKER_HOST_ROOT: str = r"C:\ip_docker"
CURRENT_CONTAINER_NAME: Optional[str] = os.environ.get("TERMINAL_CONTAINER_NAME")
CONTAINER_WORKDIR: str = "/workspace"
DEFAULT_CONTAINER_SHELL: str = "/bin/sh"
DEFAULT_WORKSPACE_NAME: str = "Workspace"
CONTAINER_PROMPT: str = "/workspace$"

# Local dictionary to track if container is being started
IS_CONTAINER_READY: Dict[str, bool] = {}


def _sanitize_workspace_name(name: Optional[str]) -> str:
    candidate = (name or DEFAULT_WORKSPACE_NAME).strip()
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .")
    return candidate or DEFAULT_WORKSPACE_NAME


def _workspace_root() -> str:
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    root = os.path.abspath(CURRENT_DIR)
    os.makedirs(root, exist_ok=True)
    return root


def _resolve_workspace_path(relative_path: Optional[str], *, allow_empty: bool = False) -> str:
    root = _workspace_root()
    raw = (relative_path or "").strip()
    normalized = raw.replace("\\", "/").strip("/")
    if not normalized:
        if allow_empty:
            return root
        raise HTTPException(status_code=400, detail="Path is required")

    target = os.path.abspath(os.path.join(root, normalized))
    try:
        if os.path.commonpath([root, target]) != root:
            raise HTTPException(status_code=400, detail="Path escapes workspace root")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    return target

# Resolve container name from websocket query params or global/env.
def _resolve_container_name(scope: Dict[str, Any]) -> Optional[str]:
    query_string = scope.get("query_string", b"")
    try:
        parsed = parse_qs(query_string.decode("utf-8"))
    except Exception:
        parsed = {}
    candidates = [
        parsed.get("container", [None])[0],
        parsed.get("container_name", [None])[0],
        parsed.get("container_id", [None])[0],
        CURRENT_CONTAINER_NAME,
        os.environ.get("TERMINAL_CONTAINER_NAME"),
    ]
    for value in candidates:
        if value:
            return value
    return None

def _ensure_workspace_dir() -> str:
    global CURRENT_DIR
    if CURRENT_DIR and os.path.isdir(CURRENT_DIR):
        return CURRENT_DIR
    os.makedirs(DOCKER_HOST_ROOT, exist_ok=True)
    default_path = os.path.join(DOCKER_HOST_ROOT, DEFAULT_WORKSPACE_NAME)
    os.makedirs(default_path, exist_ok=True)
    CURRENT_DIR = default_path
    return CURRENT_DIR

def _ensure_container_for_workspace(workspace_path: str) -> str:
    global CURRENT_CONTAINER_NAME
    user_id = "user1"
    python_version = "3.12"
    abs_path = os.path.abspath(workspace_path)
    base_name = os.path.basename(abs_path.rstrip("\\/")) or "workspace"
    digest = hashlib.sha1(abs_path.encode("utf-8")).hexdigest()[:8]
    workspace_id = f"{base_name}-{digest}"
    result = start_or_reuse_container(
        workspace_id=workspace_id,
        workspace_path=abs_path,
        student_id=user_id,
        python_version=python_version,
    )
    CURRENT_CONTAINER_NAME = result.get("container_name")
    return CURRENT_CONTAINER_NAME or ""

# Terminal session management (single websocket per browser tab)
class TerminalSession:
    def __init__(self, websocket: WebSocket, container_name: str):
        self.websocket = websocket
        self.container_name = container_name
        self.proc: Optional[subprocess.Popen] = None
        self._closed = False
        self._loop = asyncio.get_running_loop()
        self._is_windows = platform.system().lower().startswith("win")
        self._use_pty = not self._is_windows
        self._tty_enabled = not self._is_windows
        self._master_fd: Optional[int] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._pending_echoes = deque()
        self._output_buffer = ""
        self._at_prompt = False
        self._prompt_re = re.compile(rf"^{re.escape(CONTAINER_PROMPT)}\\s*$")
        self._shell_path = self._resolve_shell()
        self._chat_session: Optional[ChatbotSession] = None
        self._chat_buffer = ""

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        if self._use_pty:
            import pty  # Posix only
            self._master_fd, slave_fd = pty.openpty()
            docker_cmd = self._get_docker_exec_cmd(use_tty=True)
            # Host shell spawning is disabled for isolation.
            # shell_cmd = self._get_shell_cmd()
            self.proc = subprocess.Popen(
                docker_cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                bufsize=0,
                env=env,
            )
            os.close(slave_fd)
            self._reader_thread = threading.Thread(target=self._pump_pty_output, daemon=True)
            self._reader_thread.start()
        else:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            docker_cmd = self._get_docker_exec_cmd(use_tty=False)
            # Host shell spawning is disabled for isolation.
            # shell_cmd = self._get_shell_cmd()
            self.proc = subprocess.Popen(
                docker_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                creationflags=creationflags,
                env=env,
            )
            self._reader_thread = threading.Thread(target=self._pump_pipe_output, daemon=True)
            self._reader_thread.start()

    def _get_shell_cmd(self) -> List[str]:
        # Host shell spawning disabled for container isolation.
        # if os.name == "nt":
        #     return ["powershell.exe", "-NoLogo"]
        # shell = os.environ.get("SHELL", "/bin/bash")
        # if shell.endswith("bash") or shell.endswith("zsh"):
        #     return [shell, "-i"]
        # return [shell]
        return []

    def _resolve_shell(self) -> str:
        if self._is_windows:
            return "/bin/sh"
        env_shell = os.environ.get("TERMINAL_SHELL")
        if env_shell:
            return env_shell
        try:
            probe = subprocess.run(
                [
                    "docker",
                    "exec",
                    self.container_name,
                    "/bin/sh",
                    "-c",
                    "if [ -x /bin/bash ]; then echo /bin/bash; else echo /bin/sh; fi",
                ],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                shell_path = (probe.stdout or "").strip()
                if shell_path in ("/bin/bash", "/bin/sh"):
                    return shell_path
        except Exception:
            pass
        return "/bin/sh"

    def _get_docker_exec_cmd(self, use_tty: bool) -> List[str]:
        cmd = ["docker", "exec"]
        if use_tty:
            cmd.append("-t")
        cmd.extend(
            [
                "-i",
                "-e",
                f"PS1={CONTAINER_PROMPT}",
                "-w",
                CONTAINER_WORKDIR,
                self.container_name,
                self._shell_path,
                "-i",
            ]
        )
        return cmd

    async def send(self, text: str) -> None:
        if self._closed:
            return
        try:
            await self.websocket.send_text(text)
        except Exception:
            self._closed = True

    def _send_threadsafe(self, text: str) -> None:
        if self._closed:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.send(text), self._loop)
        except Exception:
            self._closed = True

    def _normalize_output(self, text: str) -> str:
        # Normalize line endings and strip control characters for non-TTY output.
        normalized = text.replace("\r\n", "\n").replace("\r", "")
        out_chars = []
        for ch in normalized:
            code = ord(ch)
            if ch in ("\n", "\t"):
                out_chars.append(ch)
                continue
            if code < 32 or (127 <= code < 160):
                continue
            out_chars.append(ch)
        return "".join(out_chars)

    def _pump_pty_output(self) -> None:
        if self._master_fd is None:
            return
        try:
            while True:
                rlist, _, _ = select.select([self._master_fd], [], [], 0.1)
                if not rlist:
                    if self.proc and self.proc.poll() is not None:
                        break
                    continue
                data = os.read(self._master_fd, 1024)
                if not data:
                    break
                self._send_threadsafe(data.decode("utf-8", errors="replace"))
        finally:
            self._send_threadsafe("\r\n[Terminal closed]\r\n")

    def _pump_pipe_output(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        try:
            while True:
                data = self.proc.stdout.read(1024)
                if not data:
                    break
                text = self._normalize_output(data.decode("utf-8", errors="replace"))
                self._output_buffer += text
                lines = self._output_buffer.splitlines(keepends=True)
                remainder = ""
                if lines and not (lines[-1].endswith("\n") or lines[-1].endswith("\r")):
                    remainder = lines.pop()
                self._output_buffer = ""
                for part in lines:
                    stripped = part.rstrip("\r\n")
                    if stripped and self._pending_echoes:
                        pending = self._pending_echoes[0]
                        if stripped == pending or (
                            stripped.endswith(pending) and CONTAINER_PROMPT in stripped
                        ):
                            self._pending_echoes.popleft()
                            continue
                    self._send_threadsafe(part)
                    if self._prompt_re.match(stripped):
                        self._at_prompt = True
                    elif stripped:
                        self._at_prompt = False
                if remainder:
                    self._send_threadsafe(remainder)
        finally:
            self._send_threadsafe("\r\n[Terminal closed]\r\n")

    async def handle_data(self, data: str) -> None:
        if self._chat_session:
            await self._handle_chat_data(data)
            return
        if not self.proc:
            return
        if self._use_pty and self._master_fd is not None:
            os.write(self._master_fd, data.encode("utf-8", errors="ignore"))
        else:
            if self.proc.stdin:
                send_data = data if self._tty_enabled else data.replace("\r", "\n")
                self.proc.stdin.write(send_data.encode("utf-8", errors="ignore"))
                self.proc.stdin.flush()

    async def handle_line(self, line: str) -> None:
        if self._chat_session:
            await self._handle_chat_line(line)
            return
        if not self.proc:
            return
        if self._use_pty and self._master_fd is not None:
            os.write(self._master_fd, (line + "\r").encode("utf-8", errors="ignore"))
            return
        if self.proc.stdin:
            if line.strip():
                self._pending_echoes.append(line)
            self._at_prompt = False
            suffix = "\r" if self._tty_enabled else "\n"
            self.proc.stdin.write((line + suffix).encode("utf-8", errors="ignore"))
            self.proc.stdin.flush()

    async def handle_resize(self, cols: int, rows: int) -> None:
        if not self._use_pty or self._master_fd is None:
            return
        try:
            import fcntl
            import termios
            import struct
            winsz = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsz)
        except Exception:
            pass

    async def handle_chdir(self, path: str) -> None:
        # Host directory changes are disabled for container isolation.
        # if not path:
        #     return
        # if os.path.isdir(path):
        #     self.cwd = os.path.abspath(path)
        #     await self.handle_data(f'cd "{self.cwd}"\r')
        return

    async def handle_interrupt(self) -> None:
        if not self.proc:
            return
        try:
            if self._use_pty and self._master_fd is not None:
                os.write(self._master_fd, b"\x03")
                return
            if self.proc.stdin:
                self.proc.stdin.write(b"\x03")
                self.proc.stdin.flush()
                return
            if os.name == "nt":
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.proc.send_signal(signal.SIGINT)
        except Exception:
            try:
                self.proc.terminate()
            except Exception:
                pass

    async def start_chat(self, code_context: str) -> None:
        if self._chat_session:
            await self.send("Chatbot is already running. Type exit to stop.\r\n")
            return
        diagnostics = self._chatbot_env_diagnostics()
        await self.send(diagnostics)
        if "IMPORT FAILED" in diagnostics:
            await self.send(
                "Chatbot cannot start because dependencies are missing in the backend "
                "environment. Installing inside the Docker container will not fix this.\r\n"
            )
            return
        self._chat_session = run_chatbot_menu(code_context or "")
        await self.send(self._chat_session.menu_text)

    async def _handle_chat_data(self, data: str) -> None:
        self._chat_buffer += data.replace("\r", "\n")
        while "\n" in self._chat_buffer:
            line, self._chat_buffer = self._chat_buffer.split("\n", 1)
            await self._handle_chat_line(line)

    async def _handle_chat_line(self, line: str) -> None:
        if not self._chat_session:
            return
        try:
            output, done = await self._chat_session.handle_line(line)
        except Exception as exc:
            output = (
                f"Chatbot error: {exc}\r\n"
                "Note: Chatbot runs in the backend process (FastAPI), not inside the Docker "
                "container. Install dependencies in the backend environment.\r\n"
            )
            done = True
        if output:
            await self.send(output)
        if done:
            self._chat_session = None
            self._chat_buffer = ""

    def _chatbot_env_diagnostics(self) -> str:
        python_exec = sys.executable
        api_set = bool(os.environ.get("GOOGLE_API_KEY"))
        try:
            importlib.import_module("langchain_google_genai")
            import_status = "OK"
            import_detail = ""
        except Exception as exc:
            import_status = "IMPORT FAILED"
            import_detail = f" ({exc})"
        return (
            "[Chatbot] Backend environment diagnostics:\r\n"
            f"- python executable: {python_exec}\r\n"
            f"- GOOGLE_API_KEY: {'set' if api_set else 'missing'}\r\n"
            f"- langchain_google_genai: {import_status}{import_detail}\r\n"
            "Note: Chatbot runs in the backend FastAPI process (host), not inside Docker.\r\n"
        )

    async def close(self) -> None:
        self._closed = True
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass

class PathRequest(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None

class CreateItemRequest(BaseModel):
    name: str  # Can be a relative path like 'src/test.py'
    type: str  # 'file' or 'folder'

class SaveFileRequest(BaseModel):
    file_name: str
    code_content: str

class RunFileRequest(BaseModel):
    file_name: str
    stdin_input: str = ""

class TerminalContainerRequest(BaseModel):
    container_name: str

@app.get("/pick_folder")
async def pick_folder():
    """Triggers a real Windows folder selection dialog and copies to Docker Root if needed."""
    global CURRENT_DIR
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    selected_path = filedialog.askdirectory(title="Select Folder to Open in Mini IDE")
    root.destroy()
    
    if selected_path:
        selected_path = os.path.abspath(selected_path)
        folder_name = os.path.basename(selected_path)
        target_path = os.path.join(DOCKER_HOST_ROOT, folder_name)
        
        # If the selected path is already in the DOCKER_HOST_ROOT, use it directly
        if selected_path.lower().startswith(DOCKER_HOST_ROOT.lower()):
            CURRENT_DIR = selected_path
        else:
            # Copy to DOCKER_HOST_ROOT
            os.makedirs(DOCKER_HOST_ROOT, exist_ok=True)
            
            # Simple clash prevention: if target exists, remove it first (clean slate)
            if os.path.exists(target_path):
                import time
                for i in range(3):
                    try:
                        shutil.rmtree(target_path)
                        break
                    except:
                        time.sleep(0.5)
            
            try:
                shutil.copytree(selected_path, target_path)
                CURRENT_DIR = target_path
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to copy folder: {str(e)}")
        try:
            _ensure_container_for_workspace(CURRENT_DIR)
        except Exception as e:
            print(f"Container start failed: {e}")

        return {"current_dir": CURRENT_DIR, "status": "success"}
    return {"status": "cancelled"}

@app.get("/pick_host_root")
async def pick_host_root():
    """Triggers a dialog specifically for the Docker Host Root."""
    global DOCKER_HOST_ROOT
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    selected_path = filedialog.askdirectory(title="Select Docker Host Root")
    root.destroy()
    
    if selected_path:
        DOCKER_HOST_ROOT = os.path.abspath(selected_path)
        return {"host_root": DOCKER_HOST_ROOT, "status": "success"}
    return {"status": "cancelled"}

@app.post("/create_folder_workspace")
async def create_folder_workspace(request: PathRequest):
    """Creates a new folder on the system and sets it as the workspace."""
    global CURRENT_DIR
    if request.path:
        target_path = os.path.abspath(os.path.expanduser(request.path))
    else:
        os.makedirs(DOCKER_HOST_ROOT, exist_ok=True)
        workspace_name = _sanitize_workspace_name(request.name)
        target_path = os.path.abspath(os.path.join(DOCKER_HOST_ROOT, workspace_name))
    try:
        if os.path.exists(target_path) and not os.path.isdir(target_path):
            raise HTTPException(status_code=400, detail="A file already exists at the requested workspace path")
        os.makedirs(target_path, exist_ok=True)
        CURRENT_DIR = target_path
        try:
            _ensure_container_for_workspace(CURRENT_DIR)
        except Exception as e:
            print(f"Container start failed: {e}")
        return {
            "current_dir": CURRENT_DIR,
            "workspace_name": os.path.basename(CURRENT_DIR.rstrip("\\/")) or DEFAULT_WORKSPACE_NAME,
            "status": "success",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/list_files")
async def list_files():
    """Returns the hierarchical file tree for the active workspace."""
    if not CURRENT_DIR:
        return {"files": [], "current_dir": None, "status": "no_workspace"}
    workspace_root = _workspace_root()

    def build_tree(base_path):
        nodes = []
        try:
            items = sorted(os.listdir(base_path), key=lambda x: (not os.path.isdir(os.path.join(base_path, x)), x.lower()))
            for item in items:
                path = os.path.join(base_path, item)
                rel_path = os.path.relpath(path, workspace_root).replace("\\", "/")
                is_dir = os.path.isdir(path)
                node = {
                    "name": item,
                    "path": rel_path,
                    "type": "folder" if is_dir else "file"
                }
                if is_dir:
                    node["children"] = build_tree(path)
                nodes.append(node)
        except Exception:
            pass
        return nodes

    return {"files": build_tree(workspace_root), "current_dir": workspace_root, "status": "success"}

@app.post("/create_item")
async def create_item(request: CreateItemRequest):
    """Creates a new file or folder inside the active workspace."""
    try:
        if request.type not in ("file", "folder"):
            raise HTTPException(status_code=400, detail="Invalid item type")
        target_path = _resolve_workspace_path(request.name)
        if os.path.exists(target_path):
            raise HTTPException(status_code=400, detail="Item already exists")
        
        if request.type == "folder":
            os.makedirs(target_path, exist_ok=True)
        else:
            parent_dir = os.path.dirname(target_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(target_path, "x", encoding="utf-8"):
                pass
        return {"status": "success", "path": os.path.relpath(target_path, _workspace_root()).replace("\\", "/")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/delete_item")
async def delete_item(request: PathRequest):
    """Deletes a file or folder from the workspace."""
    target_rel_path = request.path or request.name
    if not target_rel_path:
        raise HTTPException(status_code=400, detail="Path or Name is required")
    
    try:
        target_path = _resolve_workspace_path(target_rel_path)
        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail="Item not found")
        
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save_file")
async def save_file(request: SaveFileRequest):
    try:
        path = _resolve_workspace_path(request.file_name)
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(request.code_content)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/view_file")
async def view_file(file_name: str):
    try:
        path = _resolve_workspace_path(file_name)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="File not found")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"code_content": content, "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run_file")
async def run_file(request: RunFileRequest):
    try:
        file_path = _resolve_workspace_path(request.file_name)
        if not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        file_dir = os.path.dirname(file_path) or _workspace_root()
        # We ensure stdin is passed to the process
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.run(
            [sys.executable, file_path],
            cwd=file_dir,
            input=request.stdin_input if request.stdin_input else None,
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )
        return {
            "stdout": process.stdout,
            "stderr": process.stderr,
            "returncode": process.returncode,
            "status": "success"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update_host_root")
async def update_host_root(request: PathRequest):
    global DOCKER_HOST_ROOT
    if not request.path:
        raise HTTPException(status_code=400, detail="Path is required")
    DOCKER_HOST_ROOT = os.path.abspath(request.path)
    return {"status": "success", "new_root": DOCKER_HOST_ROOT}

@app.get("/get_host_root")
async def get_host_root():
    return {"host_root": DOCKER_HOST_ROOT}

@app.post("/terminal/set_container")
async def set_terminal_container(request: TerminalContainerRequest):
    global CURRENT_CONTAINER_NAME
    if not request.container_name:
        raise HTTPException(status_code=400, detail="container_name is required")
    CURRENT_CONTAINER_NAME = request.container_name
    return {"status": "success", "container_name": CURRENT_CONTAINER_NAME}

@app.post("/close_workspace")
async def close_workspace():
    """Closes the current workspace and REMOVES it if it's within the Docker Host Root."""
    global CURRENT_DIR
    if not CURRENT_DIR:
        return {"status": "success"}
    
    path_to_delete = CURRENT_DIR
    CURRENT_DIR = None # Clear immediately to avoid reuse
    
    try:
        norm_curr = os.path.normpath(path_to_delete).lower()
        norm_root = os.path.normpath(DOCKER_HOST_ROOT).lower()
        
        # Check if the project is inside DOCKER_HOST_ROOT
        if norm_curr.startswith(norm_root) and len(norm_curr) > len(norm_root):
            if os.path.exists(path_to_delete):
                # Retry loop to handle Windows file locks (e.g. while Docker is stopping)
                import time
                for i in range(5):
                    try:
                        shutil.rmtree(path_to_delete)
                        print(f"Cleanup: removed {path_to_delete}")
                        break
                    except Exception as e:
                        print(f"Cleanup retry {i+1} failed: {e}")
                        time.sleep(1)
    except Exception as e:
        print(f"Cleanup Error: {e}")
    
    return {"status": "success"}

@app.get("/mini_ide")
async def mini_ide():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


@app.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        container_name = _resolve_container_name(websocket.scope)
        if not container_name:
            workspace_path = _ensure_workspace_dir()
            container_name = _ensure_container_for_workspace(workspace_path)
        if not container_name:
            await websocket.send_text("[Terminal error] Failed to resolve container.\r\n")
            await websocket.close()
            return
        session = TerminalSession(websocket, container_name=container_name)
    except Exception as e:
        await websocket.send_text(f"[Terminal error] {e}\r\n")
        await websocket.close()
        return
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except Exception:
                payload = {"type": "data", "data": message}

            msg_type = payload.get("type")
            if msg_type == "data":
                await session.handle_data(payload.get("data", ""))
            elif msg_type == "line":
                await session.handle_line(payload.get("data", ""))
            elif msg_type == "chat":
                await session.start_chat(payload.get("code_context", ""))
            elif msg_type == "resize":
                await session.handle_resize(int(payload.get("cols", 80)), int(payload.get("rows", 24)))
            elif msg_type == "chdir":
                await session.handle_chdir(payload.get("data", ""))
            elif msg_type == "interrupt":
                await session.handle_interrupt()
            else:
                await session.handle_data(payload.get("data", ""))
    except WebSocketDisconnect:
        await session.close()
    except Exception:
        await session.close()
