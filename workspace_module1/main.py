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
import shlex
import zipfile
from urllib.parse import parse_qs
from collections import deque
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from workspace_module2.container_manager import start_or_reuse_container, start_or_reuse_container_for_path
from workspace_module1.chatbot import run_chatbot_menu, ChatbotSession
# import tkinter as tk (Moved to local scope)
# from tkinter import filedialog (Moved to local scope)

load_dotenv()

app = FastAPI()

# Global state
CURRENT_DIR: Optional[str] = None
WORKSPACE_ROOT: str = os.path.abspath(os.getenv("WORKSPACE_ROOT", r"C:\ip_docker\Workspace"))
CURRENT_CONTAINER_NAME: Optional[str] = os.environ.get("TERMINAL_CONTAINER_NAME")
CONTAINER_WORKDIR: str = "/workspace"
DEFAULT_CONTAINER_SHELL: str = "/bin/sh"
DEFAULT_WORKSPACE_NAME: str = "Workspace"
CONTAINER_PROMPT: str = "/workspace$"
MAX_TEXT_FILE_BYTES: int = int(os.environ.get("MAX_TEXT_FILE_BYTES", 2 * 1024 * 1024))
ALLOWED_PYTHON_VERSIONS = {"3.10", "3.11", "3.12"}
WORKSPACE_RUNTIME: Dict[str, Dict[str, str]] = {}

TEXT_EXTENSIONS = {
    ".py",
    ".csv",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
}
NOTEBOOK_EXTENSIONS = {".ipynb"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
BINARY_EXTENSIONS = {".pkl", ".pt"}
SPECIAL_TEXT_NAMES = {"requirements.txt"}

os.makedirs(WORKSPACE_ROOT, exist_ok=True)

CONTAINER_PTY_BRIDGE_SCRIPT = r"""
import os
import pty
import select
import signal
import sys
import tempfile

shell = os.environ.get("MINI_IDE_SHELL", "/bin/sh")
workdir = os.environ.get("MINI_IDE_WORKDIR", "/workspace")
term = os.environ.get("TERM", "xterm-256color")

try:
    os.chdir(workdir)
except Exception:
    pass

pid, master_fd = pty.fork()
if pid == 0:
    os.environ["TERM"] = term
    if os.path.basename(shell) == "bash":
        fd, inputrc_path = tempfile.mkstemp(prefix="miniide_inputrc_")
        with os.fdopen(fd, "w", encoding="utf-8") as inputrc:
            inputrc.write("set enable-bracketed-paste off\n")
        os.environ["INPUTRC"] = inputrc_path
    os.execv(shell, [shell, "-i"])

stdin_fd = sys.stdin.fileno()
stdout = sys.stdout.buffer

while True:
    try:
        readable, _, _ = select.select([master_fd, stdin_fd], [], [])
    except OSError:
        break

    if master_fd in readable:
        try:
            data = os.read(master_fd, 4096)
        except OSError:
            break
        if not data:
            break
        stdout.write(data)
        stdout.flush()

    if stdin_fd in readable:
        try:
            data = os.read(stdin_fd, 4096)
        except OSError:
            break
        if not data:
            try:
                os.kill(pid, signal.SIGHUP)
            except OSError:
                pass
            break
        os.write(master_fd, data)
"""

# Local dictionary to track if container is being started
IS_CONTAINER_READY: Dict[str, bool] = {}

def _workspace_key(path: Optional[str]) -> str:
    if not path:
        return ""
    return os.path.abspath(path)

def _get_runtime(workspace_path: Optional[str]) -> Dict[str, str]:
    key = _workspace_key(workspace_path)
    return WORKSPACE_RUNTIME.get(key, {})

def _set_runtime(workspace_path: Optional[str], runtime: Dict[str, str]) -> None:
    key = _workspace_key(workspace_path)
    if not key:
        return
    WORKSPACE_RUNTIME[key] = runtime

def _sanitize_workspace_name(name: Optional[str]) -> str:
    candidate = (name or DEFAULT_WORKSPACE_NAME).strip()
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .")
    return candidate or DEFAULT_WORKSPACE_NAME

def _workspace_root() -> str:
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    root = os.path.abspath(CURRENT_DIR)
    try:
        if os.path.commonpath([WORKSPACE_ROOT, root]) != WORKSPACE_ROOT:
            raise HTTPException(status_code=400, detail="Workspace is outside WORKSPACE_ROOT")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace root")
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

def _resolve_workspace_folder_from_name(workspace_name: str) -> str:
    raw_name = (workspace_name or "").strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="workspace_name required")
    if ".." in raw_name or "/" in raw_name or "\\" in raw_name:
        raise HTTPException(status_code=400, detail="Invalid workspace_name")

    safe_name = _sanitize_workspace_name(raw_name)
    workspace_path = os.path.abspath(os.path.join(WORKSPACE_ROOT, safe_name))
    try:
        if os.path.commonpath([WORKSPACE_ROOT, workspace_path]) != WORKSPACE_ROOT:
            raise HTTPException(status_code=400, detail="Invalid workspace_name")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace_name")
    return workspace_path

def zip_workspace(workspace_name: str):
    workspace_path = _resolve_workspace_folder_from_name(workspace_name)

    if not os.path.exists(workspace_path) or not os.path.isdir(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")

    safe_name = os.path.basename(workspace_path.rstrip("\\/"))
    zip_path = os.path.abspath(os.path.join(WORKSPACE_ROOT, f"{safe_name}.zip"))
    try:
        if os.path.commonpath([WORKSPACE_ROOT, zip_path]) != WORKSPACE_ROOT:
            raise HTTPException(status_code=400, detail="Invalid workspace_name")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace_name")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(workspace_path):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, workspace_path)
                zipf.write(full_path, arcname)

    return zip_path

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
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    default_path = os.path.join(WORKSPACE_ROOT, DEFAULT_WORKSPACE_NAME)
    os.makedirs(default_path, exist_ok=True)
    CURRENT_DIR = default_path
    return CURRENT_DIR

def _ensure_container_for_workspace(workspace_path: str) -> str:
    global CURRENT_CONTAINER_NAME
    runtime = _get_runtime(workspace_path)
    python_version = (runtime.get("python_version") or "").strip()
    if not python_version:
        raise RuntimeError("Python version not selected")
    user_id = runtime.get("user_id") or "user1"
    project_id = runtime.get("project_id") or (os.path.basename(workspace_path) or "workspace")
    result = start_or_reuse_container_for_path(
        workspace_path=workspace_path,
        user_id=user_id,
        project_id=project_id,
        python_version=python_version,
    )
    runtime["user_id"] = user_id
    runtime["project_id"] = project_id
    runtime["python_version"] = python_version
    runtime["container_name"] = result.get("container_name") or ""
    _set_runtime(workspace_path, runtime)
    CURRENT_CONTAINER_NAME = runtime.get("container_name")
    return CURRENT_CONTAINER_NAME or ""

def _safe_workspace_path(rel_path: str) -> str:
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    if not rel_path:
        raise HTTPException(status_code=400, detail="Path is required")
    if "\x00" in rel_path:
        raise HTTPException(status_code=400, detail="Invalid path")
    if os.path.isabs(rel_path) or re.match(r"^[a-zA-Z]:", rel_path):
        raise HTTPException(status_code=400, detail="Path must be relative to workspace")
    norm_rel = os.path.normpath(rel_path).lstrip("\\/")
    abs_path = os.path.abspath(os.path.join(CURRENT_DIR, norm_rel))
    root = os.path.abspath(CURRENT_DIR)
    try:
        common = os.path.commonpath([root, abs_path])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    if common != root:
        raise HTTPException(status_code=400, detail="Path escapes workspace")
    return abs_path

def _is_probably_binary(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(4096)
        if not chunk:
            return False
        if b"\x00" in chunk:
            return True
        nontext = 0
        for b in chunk:
            if b in (9, 10, 13):
                continue
            if 32 <= b <= 126:
                continue
            if b >= 128:
                continue
            nontext += 1
        return (nontext / max(len(chunk), 1)) > 0.3
    except Exception:
        return False

def _classify_path(path: str, allow_missing: bool = False) -> Dict[str, Any]:
    base_original = os.path.basename(path)
    base = base_original.lower()
    ext = os.path.splitext(base)[1]
    category = "text"
    preview = None
    if base in SPECIAL_TEXT_NAMES:
        category = "text"
    elif ext in NOTEBOOK_EXTENSIONS:
        category = "notebook"
    elif ext in IMAGE_EXTENSIONS:
        category = "image"
        preview = "image"
    elif ext in BINARY_EXTENSIONS:
        category = "binary"
        preview = "binary"
    elif ext in TEXT_EXTENSIONS:
        category = "text"
    else:
        if not allow_missing and os.path.exists(path) and _is_probably_binary(path):
            category = "binary"
            preview = "binary"
    editable = category in ("text", "notebook")
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if editable and size > MAX_TEXT_FILE_BYTES:
        editable = False
        preview = "large"
    return {
        "name": base_original,
        "extension": ext.lstrip("."),
        "category": category,
        "editable": editable,
        "preview": preview,
        "size": size,
    }

# Terminal session management (single websocket per browser tab)
class TerminalSession:
    def __init__(self, websocket: WebSocket, container_name: Optional[str], workspace_path: Optional[str]):
        self.websocket = websocket
        self.container_name = container_name
        self.workspace_path = workspace_path
        self.proc: Optional[subprocess.Popen] = None
        self._closed = False
        self._loop = asyncio.get_running_loop()
        self._reader_thread: Optional[threading.Thread] = None
        self._shell_path = self._resolve_shell()
        self._chat_session: Optional[ChatbotSession] = None
        self._chat_buffer = ""
        self._cols = 80
        self._rows = 24
        self._version_required_notice_sent = False

        if self.container_name:
            self._start_process()

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
                    "if command -v bash >/dev/null 2>&1; then command -v bash; "
                    "elif [ -x /bin/bash ]; then echo /bin/bash; else echo /bin/sh; fi",
                ],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                shell_path = (probe.stdout or "").strip().splitlines()[-1].strip()
                if shell_path and (shell_path.endswith("bash") or shell_path == "/bin/sh"):
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
                f"PS1={CONTAINER_PROMPT} ",
                "-w",
                CONTAINER_WORKDIR,
                self.container_name,
            ]
        )
        shell_path = self._shell_path or "/bin/sh"
        shell_args = ["-i"]
        if shell_path.endswith("bash"):
            shell_args = ["--noprofile", "--norc", "-i"]

        prompt_value = f"{CONTAINER_PROMPT} "
        prompt_export = f"export PS1={shlex.quote(prompt_value)}"
        shell_cmd = " ".join(shlex.quote(part) for part in [shell_path, *shell_args])
        base_cmd = f"{prompt_export}; stty -echo 2>/dev/null; exec {shell_cmd}"

        if use_tty:
            cmd.extend(["/bin/sh", "-lc", base_cmd])
            return cmd

        # Use script(1) to allocate a PTY inside the container when host TTY is unavailable.
        wrapper = (
            "if command -v script >/dev/null 2>&1; then "
            f"exec script -q /dev/null -c {shlex.quote(base_cmd)}; "
            f"else exec /bin/sh -lc {shlex.quote(base_cmd)}; fi"
        )
        cmd.extend(["/bin/sh", "-lc", wrapper])
        return cmd

    def _start_process(self) -> None:
        if self.proc or not self.container_name:
            return

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            self._get_docker_exec_cmd(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=creationflags,
            env=env,
        )
        self._reader_thread = threading.Thread(target=self._pump_output, daemon=True)
        self._reader_thread.start()

    async def _ensure_started(self) -> bool:
        if self.proc:
            return True

        runtime = _get_runtime(self.workspace_path)
        python_version = (runtime.get("python_version") or "").strip()
        if not python_version:
            if not self._version_required_notice_sent:
                await self.send(
                    "Python version not selected. Please choose Python 3.10 / 3.11 / 3.12 before using terminal.\r\n"
                )
                self._version_required_notice_sent = True
            return False

        if not runtime.get("container_name"):
            try:
                _ensure_container_for_workspace(self.workspace_path or "")
            except Exception as exc:
                await self.send(f"[Terminal error] {exc}\r\n")
                return False
            runtime = _get_runtime(self.workspace_path)

        self.container_name = runtime.get("container_name")
        if not self.container_name:
            await self.send("[Terminal error] Container is not available.\r\n")
            return False

        self._shell_path = self._resolve_shell()
        self._start_process()
        return self.proc is not None

    def _resolve_shell(self) -> str:
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
        return DEFAULT_CONTAINER_SHELL

    def _get_docker_exec_cmd(self) -> List[str]:
        return [
            "docker",
            "exec",
            "-i",
            "-e",
            f"MINI_IDE_SHELL={self._shell_path}",
            "-e",
            f"MINI_IDE_WORKDIR={CONTAINER_WORKDIR}",
            "-e",
            "TERM=xterm-256color",
            "-w",
            CONTAINER_WORKDIR,
            self.container_name,
            "python",
            "-u",
            "-c",
            CONTAINER_PTY_BRIDGE_SCRIPT,
        ]

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

    def _pump_output(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        try:
            while True:
                data = self.proc.stdout.read(4096)
                if not data:
                    break
                self._send_threadsafe(data.decode("utf-8", errors="replace"))
        finally:
            self._send_threadsafe("\r\n[Terminal closed]\r\n")

    async def handle_data(self, data: str) -> None:
        if self._chat_session:
            await self._handle_chat_data(data)
            return
        if not await self._ensure_started():
            return
        if not self.proc or not self.proc.stdin:
            return
        self.proc.stdin.write(data.encode("utf-8", errors="ignore"))
        self.proc.stdin.flush()

    async def handle_line(self, line: str) -> None:
        if self._chat_session:
            await self._handle_chat_line(line)
            return
        await self.handle_data(line + "\r")

    async def handle_resize(self, cols: int, rows: int) -> None:
        self._cols = max(20, int(cols or 80))
        self._rows = max(5, int(rows or 24))

    async def handle_chdir(self, path: str) -> None:
        return

    async def handle_interrupt(self) -> None:
        if not self.proc or not self.proc.stdin:
            return
        try:
            self.proc.stdin.write(b"\x03")
            self.proc.stdin.flush()
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

class TerminalContainerRequest(BaseModel):
    container_name: str

class RenameItemRequest(BaseModel):
    old_path: str
    new_path: str

class SelectPythonVersionRequest(BaseModel):
    user_id: str
    project_id: str
    python_version: str

@app.get("/pick_folder")
async def pick_folder():
    """Triggers a real Windows folder selection dialog and copies to WORKSPACE_ROOT if needed."""
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
        target_path = os.path.join(WORKSPACE_ROOT, folder_name)
        
        # If the selected path is already in WORKSPACE_ROOT, use it directly
        in_workspace_root = False
        try:
            in_workspace_root = os.path.commonpath([WORKSPACE_ROOT, selected_path]) == WORKSPACE_ROOT
        except ValueError:
            in_workspace_root = False
        if in_workspace_root:
            CURRENT_DIR = selected_path
        else:
            # Copy to WORKSPACE_ROOT
            os.makedirs(WORKSPACE_ROOT, exist_ok=True)
            
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
        global CURRENT_CONTAINER_NAME
        CURRENT_CONTAINER_NAME = None

        return {"current_dir": CURRENT_DIR, "status": "success"}
    return {"status": "cancelled"}

@app.get("/pick_host_root")
async def pick_host_root():
    """Triggers a dialog specifically for the workspace root."""
    global WORKSPACE_ROOT
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    selected_path = filedialog.askdirectory(title="Select Workspace Root")
    root.destroy()
    
    if selected_path:
        WORKSPACE_ROOT = os.path.abspath(selected_path)
        os.makedirs(WORKSPACE_ROOT, exist_ok=True)
        return {"host_root": WORKSPACE_ROOT, "status": "success"}
    return {"status": "cancelled"}

@app.post("/create_folder_workspace")
async def create_folder_workspace(request: PathRequest):
    """Creates a new folder on the system and sets it as the workspace."""
    global CURRENT_DIR
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    if request.path:
        target_path = os.path.abspath(os.path.expanduser(request.path))
        try:
            if os.path.commonpath([WORKSPACE_ROOT, target_path]) != WORKSPACE_ROOT:
                raise HTTPException(status_code=400, detail="Workspace path must be inside WORKSPACE_ROOT")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workspace path")
    else:
        workspace_name = _sanitize_workspace_name(request.name)
        target_path = os.path.abspath(os.path.join(WORKSPACE_ROOT, workspace_name))
    try:
        if os.path.exists(target_path) and not os.path.isdir(target_path):
            raise HTTPException(status_code=400, detail="A file already exists at the requested workspace path")
        os.makedirs(target_path, exist_ok=True)
        CURRENT_DIR = target_path
        global CURRENT_CONTAINER_NAME
        CURRENT_CONTAINER_NAME = None
        return {
            "current_dir": CURRENT_DIR,
            "workspace_name": os.path.basename(CURRENT_DIR.rstrip("\\/")) or DEFAULT_WORKSPACE_NAME,
            "status": "success",
        }
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

    runtime = _get_runtime(CURRENT_DIR)
    runtime_payload = {
        "python_version": runtime.get("python_version"),
        "locked": bool(runtime.get("python_version")),
    }
    return {
        "files": build_tree(workspace_root),
        "current_dir": workspace_root,
        "status": "success",
        "runtime": runtime_payload,
    }

@app.post("/select_python_version")
async def select_python_version(request: SelectPythonVersionRequest):
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    version = (request.python_version or "").strip()
    if version not in ALLOWED_PYTHON_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid python_version. Allowed: 3.10, 3.11, 3.12",
        )
    runtime = _get_runtime(CURRENT_DIR)
    locked = runtime.get("python_version")
    if locked and locked != version:
        raise HTTPException(
            status_code=400,
            detail=f"Python version already locked to {locked}",
        )
    runtime["python_version"] = locked or version
    runtime["user_id"] = (request.user_id or "user1").strip()
    runtime["project_id"] = (request.project_id or "workspace").strip()
    _set_runtime(CURRENT_DIR, runtime)
    try:
        _ensure_container_for_workspace(CURRENT_DIR)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    runtime = _get_runtime(CURRENT_DIR)
    return {
        "status": "success",
        "python_version": runtime.get("python_version"),
        "locked": True,
        "container_name": runtime.get("container_name"),
    }

@app.post("/create_item")
async def create_item(request: CreateItemRequest):
    """Creates a new file or folder inside the active workspace."""
    try:
        if request.type not in ("file", "folder"):
            raise HTTPException(status_code=400, detail="Invalid item type")
        target_path = _safe_workspace_path(request.name)
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
        return {
                    "status": "success",
                    "path": os.path.relpath(target_path, _workspace_root()).replace("\\", "/")
                }
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
        target_path = _safe_workspace_path(target_rel_path)
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
        path = _safe_workspace_path(request.file_name)
        if os.path.isdir(path):
            raise HTTPException(status_code=400, detail="Path is a directory")
        meta = _classify_path(path, allow_missing=True)
        if meta["category"] in ("binary", "image"):
            raise HTTPException(status_code=400, detail="Binary/image files cannot be edited")
        os.makedirs(os.path.dirname(path), exist_ok=True)
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
        path = _safe_workspace_path(file_name)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File not found")
        if os.path.isdir(path):
            raise HTTPException(status_code=400, detail="Path is a directory")
        meta = _classify_path(path)
        meta["path"] = os.path.relpath(path, CURRENT_DIR).replace("\\", "/")
        if meta["preview"] == "image":
            return {
                "status": "success",
                "file": meta,
                "message": "Image preview available.",
            }
        if meta["preview"] == "binary":
            return {
                "status": "success",
                "file": meta,
                "message": "Binary file cannot be edited.",
            }
        if meta["preview"] == "large":
            return {
                "status": "success",
                "file": meta,
                "message": f"File is too large to open in editor ({meta['size']} bytes).",
            }
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"code_content": content, "file": meta, "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/file_preview")
async def file_preview(file_name: str):
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    path = _safe_workspace_path(file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    if os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Path is a directory")
    meta = _classify_path(path)
    if meta["category"] != "image":
        raise HTTPException(status_code=400, detail="Preview not supported")
    return FileResponse(path)

@app.post("/rename_item")
async def rename_item(request: RenameItemRequest):
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    if not request.old_path or not request.new_path:
        raise HTTPException(status_code=400, detail="Paths are required")
    try:
        src = _safe_workspace_path(request.old_path)
        dst = _safe_workspace_path(request.new_path)
        if not os.path.exists(src):
            raise HTTPException(status_code=404, detail="Item not found")
        if os.path.exists(dst):
            raise HTTPException(status_code=400, detail="Target already exists")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        return {"status": "success"}
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
    global WORKSPACE_ROOT
    if not request.path:
        raise HTTPException(status_code=400, detail="Path is required")
    WORKSPACE_ROOT = os.path.abspath(request.path)
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    return {"status": "success", "new_root": WORKSPACE_ROOT}

@app.get("/get_host_root")
async def get_host_root():
    return {"host_root": WORKSPACE_ROOT}

@app.post("/zip_workspace")
def zip_workspace_api(data: dict):
    workspace_name = data.get("workspace_name")

    if not workspace_name:
        raise HTTPException(status_code=400, detail="workspace_name required")

    zip_path = zip_workspace(workspace_name)

    return {
        "message": "Workspace zipped successfully",
        "zip_path": zip_path
    }

@app.post("/terminal/set_container")
async def set_terminal_container(request: TerminalContainerRequest):
    global CURRENT_CONTAINER_NAME
    if not request.container_name:
        raise HTTPException(status_code=400, detail="container_name is required")
    CURRENT_CONTAINER_NAME = request.container_name
    return {"status": "success", "container_name": CURRENT_CONTAINER_NAME}

@app.post("/close_workspace")
async def close_workspace():
    """Closes the current workspace and REMOVES it if it's within WORKSPACE_ROOT."""
    global CURRENT_DIR
    global CURRENT_CONTAINER_NAME
    if not CURRENT_DIR:
        return {"status": "success"}
    
    path_to_delete = CURRENT_DIR
    CURRENT_DIR = None # Clear immediately to avoid reuse
    CURRENT_CONTAINER_NAME = None
    WORKSPACE_RUNTIME.pop(_workspace_key(path_to_delete), None)
    
    try:
        norm_curr = os.path.normpath(path_to_delete)
        norm_root = os.path.normpath(WORKSPACE_ROOT)
        inside_root = False
        try:
            inside_root = os.path.commonpath([norm_root, norm_curr]) == norm_root and norm_curr != norm_root
        except ValueError:
            inside_root = False
        
        # Check if the project is inside WORKSPACE_ROOT
        if inside_root:
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
        workspace_path = _ensure_workspace_dir()
        runtime = _get_runtime(workspace_path)
        container_name = None
        if runtime.get("python_version"):
            container_name = runtime.get("container_name") or _resolve_container_name(websocket.scope)
            if not container_name:
                try:
                    container_name = _ensure_container_for_workspace(workspace_path)
                except Exception:
                    container_name = None
        session = TerminalSession(
            websocket,
            container_name=container_name,
            workspace_path=workspace_path,
        )
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
            if msg_type in ("data", "input"):
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
