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

def _run_shell_command(cmd: str) -> Dict[str, str]:
    process = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip() or f"Command failed: {cmd}")
    return {
        "stdout": process.stdout,
        "stderr": process.stderr,
    }

def _sanitize_container_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", str(value).strip())

def _normalize_docker_mount_path(project_path: str) -> str:
    return os.path.abspath(project_path).replace("\\", "/")

def _container_name_for(user_id: str, project_id: str) -> str:
    return f"{_sanitize_container_name(user_id)}_{_sanitize_container_name(project_id)}"

def _docker_running_container_names() -> List[str]:
    result = _run_shell_command('docker ps --format "{{.Names}}"')
    return [line.strip() for line in result["stdout"].splitlines() if line.strip()]

def _docker_all_container_names() -> List[str]:
    result = _run_shell_command('docker ps -a --format "{{.Names}}"')
    return [line.strip() for line in result["stdout"].splitlines() if line.strip()]

def _start_project_container(user_id: str, project_id: str, python_version: str, project_path: str) -> Dict[str, str]:
    global CURRENT_CONTAINER_NAME

    if not user_id or not project_id or not python_version or not project_path:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: userId, projectId, pythonVersion, projectPath",
        )

    python_version = str(python_version).strip()
    if python_version not in ALLOWED_PYTHON_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid pythonVersion. Allowed: 3.10, 3.11, 3.12",
        )

    abs_project_path = os.path.abspath(project_path)
    if not os.path.isdir(abs_project_path):
        raise HTTPException(status_code=404, detail="projectPath does not exist or is not a folder")

    container_name = _container_name_for(user_id, project_id)
    image = f"ide-python-{python_version}"

    try:
        _run_shell_command("docker info")
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Docker is not running or not accessible. Please start Docker Desktop.",
        )

    try:
        existing = _docker_all_container_names()
        if container_name in existing:
            running = _docker_running_container_names()
            if container_name in running:
                CURRENT_CONTAINER_NAME = container_name
                return {
                    "status": "success",
                    "message": "Container already running",
                    "container_name": container_name,
                    "image": image,
                }
            _run_shell_command(f"docker start {shlex.quote(container_name)}")
            CURRENT_CONTAINER_NAME = container_name
            return {
                "status": "success",
                "message": "Container restarted",
                "container_name": container_name,
                "image": image,
            }
    except HTTPException:
        raise
    except Exception:
        pass

    normalized_path = _normalize_docker_mount_path(abs_project_path)
    run_cmd = (
        "docker run -itd "
        f"--name {shlex.quote(container_name)} "
        '--cpus="0.5" -m 512m --pids-limit 100 '
        f'-v "{normalized_path}:/workspace" '
        "-w /workspace "
        f"{shlex.quote(image)} tail -f /dev/null"
    )

    try:
        _run_shell_command(run_cmd)
        CURRENT_CONTAINER_NAME = container_name
        return {
            "status": "success",
            "message": "Container created and started successfully",
            "container_name": container_name,
            "image": image,
        }
    except Exception as exc:
        err_text = str(exc).lower()
        if (
            "not found" in err_text
            or "manifest unknown" in err_text
            or "pull access denied" in err_text
        ):
            raise HTTPException(
                status_code=404,
                detail=f"Image {image} not found. Build ide-python-{python_version} first.",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start container: {exc}",
        )

def _execute_command_in_container(user_id: str, project_id: str, command: str, working_dir: Optional[str] = None) -> Dict[str, str]:
    if not user_id or not project_id or not command:
        raise HTTPException(status_code=400, detail="Missing required fields")

    container_name = _container_name_for(user_id, project_id)

    try:
        running = _docker_running_container_names()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check container status: {exc}",
        )

    if container_name not in running:
        raise HTTPException(
            status_code=404,
            detail="Container is not running. Please start the project first.",
        )

    command_with_cwd = command
    if working_dir and str(working_dir).strip():
        escaped_dir = str(working_dir).strip().replace('"', '\\"')
        command_with_cwd = f'cd "{escaped_dir}" && {command}'

    escaped_command = command_with_cwd.replace('"', '\\"')
    exec_cmd = f'docker exec {shlex.quote(container_name)} sh -c "{escaped_command}"'

    process = subprocess.run(
        exec_cmd,
        shell=True,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    if process.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail="Command execution failed or returned error exit code",
        )

    return {
        "status": "success",
        "stdout": process.stdout,
        "stderr": process.stderr,
    }

def _stop_project_container(user_id: str, project_id: str) -> Dict[str, str]:
    global CURRENT_CONTAINER_NAME

    if not user_id or not project_id:
        raise HTTPException(status_code=400, detail="Missing required fields")

    container_name = _container_name_for(user_id, project_id)

    stop_process = subprocess.run(
        f"docker stop {shlex.quote(container_name)}",
        shell=True,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    stop_err = (stop_process.stderr or "").lower()
    if stop_process.returncode != 0 and "no such container" not in stop_err:
        raise HTTPException(
            status_code=500,
            detail=stop_process.stderr.strip() or stop_process.stdout.strip() or "Failed to stop container",
        )

    rm_process = subprocess.run(
        f"docker rm {shlex.quote(container_name)}",
        shell=True,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    rm_err = (rm_process.stderr or "").lower()
    if rm_process.returncode != 0:
        if "no such container" in rm_err:
            if CURRENT_CONTAINER_NAME == container_name:
                CURRENT_CONTAINER_NAME = None
            return {
                "status": "success",
                "message": "Container already stopped and removed",
            }
        raise HTTPException(
            status_code=500,
            detail=rm_process.stderr.strip() or rm_process.stdout.strip() or "Failed to remove container",
        )

    if CURRENT_CONTAINER_NAME == container_name:
        CURRENT_CONTAINER_NAME = None

    return {
        "status": "success",
        "message": "Container stopped and removed successfully",
    }
    
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

    result = _start_project_container(
        user_id=user_id,
        project_id=project_id,
        python_version=python_version,
        project_path=workspace_path,
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
        self._last_code_context = ""
        self._line_buffer = ""
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

    def update_code_context(self, code_context: str) -> None:
        cleaned_context = (code_context or "").strip()
        if cleaned_context:
            self._last_code_context = code_context

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

    async def start_chat(self, code_context: str) -> None:
        if self._chat_session:
            await self.send("Chatbot is already running. Type exit or Ctrl+C to stop.\r\n")
            return
        try:
            cleaned_context = (code_context or "").strip()
            if cleaned_context:
                self._last_code_context = code_context
            effective_context = self._last_code_context or ""
            if not effective_context.strip():
                effective_context = "No active editor code was provided."
                await self.send("\r\nChatbot started. No active editor code was provided.\r\n")
            self._chat_session = run_chatbot_menu(effective_context)
        except Exception as exc:
            await self.send(f"Chatbot error: {exc}\r\n")
            await self.send(self._chatbot_env_diagnostics())
            self._chat_session = None
            return
        self._chat_buffer = ""
        await self.send("\r\n" + self._chat_session.menu_text)

    async def handle_data(self, data: str) -> None:
        if self._chat_session:
            await self._handle_chat_data(data)
            return
        if not await self._ensure_started():
            return
        if not self.proc or not self.proc.stdin:
            return
        if not data:
            return

        forward = []
        idx = 0
        length = len(data)
        while idx < length:
            ch = data[idx]
            if ch == "\r" or ch == "\n":
                if ch == "\r" and idx + 1 < length and data[idx + 1] == "\n":
                    idx += 1
                line = self._line_buffer.strip()
                self._line_buffer = ""
                if line.lower() == "chat":
                    if forward:
                        self.proc.stdin.write("".join(forward).encode("utf-8", errors="ignore"))
                        self.proc.stdin.flush()
                        forward = []
                    try:
                        self.proc.stdin.write(b"\x15")
                        self.proc.stdin.flush()
                    except Exception:
                        pass
                    await self.start_chat("")
                    remaining = data[idx + 1 :]
                    if remaining:
                        await self._handle_chat_data(remaining)
                    return
                forward.append(ch)
                idx += 1
                continue

            if ch in ("\x08", "\x7f"):
                if self._line_buffer:
                    self._line_buffer = self._line_buffer[:-1]
            elif ch == "\x15":
                self._line_buffer = ""
            elif ch == "\x03":
                self._line_buffer = ""
            elif ch != "\x1b" and ch.isprintable():
                self._line_buffer += ch

            forward.append(ch)
            idx += 1

        if forward:
            self.proc.stdin.write("".join(forward).encode("utf-8", errors="ignore"))
            self.proc.stdin.flush()

    async def handle_resize(self, cols: int, rows: int) -> None:
        self._cols = max(20, int(cols or 80))
        self._rows = max(5, int(rows or 24))

    async def handle_chdir(self, path: str) -> None:
        return

    async def handle_interrupt(self) -> None:
        if self._chat_session:
            self._chat_session = None
            self._chat_buffer = ""
            await self.send("^C\r\nExited chatbot.\r\n")
            return

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


    async def handle_line(self, line: str) -> None:
        line = line.strip()

        if line.lower() == "chat":
            await self.start_chat("")
            return

        if self._chat_session:
            if line.lower() == "exit":
                self._chat_session = None
                self._chat_buffer = ""
                await self.send("Exited chatbot.\r\n")
                return
            await self._handle_chat_line(line)
            return

        await self.handle_data(line + "\r")

    async def _handle_chat_data(self, data: str) -> None:
        if not self._chat_session:
            return

        for ch in data:
            # Ctrl+C -> exit chatbot mode
            if ch == "\x03":
                self._chat_session = None
                self._chat_buffer = ""
                await self.send("^C\r\nExited chatbot.\r\n")
                return

            # Enter -> process one line
            if ch in ("\r", "\n"):
                line = self._chat_buffer.strip()
                self._chat_buffer = ""
                await self.send("\r\n")
                if line:
                    await self._handle_chat_line(line)
                continue

            # Backspace / Delete
            if ch in ("\x08", "\x7f"):
                if self._chat_buffer:
                    self._chat_buffer = self._chat_buffer[:-1]
                    await self.send("\b \b")
                continue

            # Ctrl+U clear line
            if ch == "\x15":
                while self._chat_buffer:
                    self._chat_buffer = self._chat_buffer[:-1]
                    await self.send("\b \b")
                continue

            # Printable characters
            if ch.isprintable():
                self._chat_buffer += ch
                await self.send(ch)

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
    stdin_input: Optional[str] = None

class TerminalContainerRequest(BaseModel):
    container_name: str

class RenameItemRequest(BaseModel):
    old_path: str
    new_path: str

class SelectPythonVersionRequest(BaseModel):
    user_id: str
    project_id: str
    python_version: str
    
class StartProjectRequest(BaseModel):
    userId: str
    projectId: str
    pythonVersion: str
    projectPath: str

class ExecuteCommandRequest(BaseModel):
    userId: str
    projectId: str
    command: str
    workingDir: Optional[str] = None

class StopProjectRequest(BaseModel):
    userId: str
    projectId: str
    
class AttachLocalDatasetRequest(BaseModel):
    workspace_name: str
    source_file_path: str
    
@app.post("/attach_local_dataset")
async def attach_local_dataset(request: AttachLocalDatasetRequest):
    try:
        workspace_path = _resolve_workspace_folder_from_name(request.workspace_name)

        if not os.path.exists(workspace_path) or not os.path.isdir(workspace_path):
            raise HTTPException(status_code=404, detail="Workspace not found")

        source_path = os.path.abspath(request.source_file_path)

        if not os.path.exists(source_path) or not os.path.isfile(source_path):
            raise HTTPException(status_code=404, detail="Source dataset file not found")

        file_name = os.path.basename(source_path)
        target_path = os.path.join(workspace_path, file_name)

        shutil.copy2(source_path, target_path)

        return {
            "status": "success",
            "message": "Dataset attached successfully",
            "workspace_name": request.workspace_name,
            "file_name": file_name,
            "target_path": target_path
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
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

@app.post("/start-project")
async def start_project(request: StartProjectRequest):
    result = _start_project_container(
        user_id=request.userId,
        project_id=request.projectId,
        python_version=request.pythonVersion,
        project_path=request.projectPath,
    )

    workspace_abs = os.path.abspath(request.projectPath)
    runtime = _get_runtime(workspace_abs)
    runtime["user_id"] = request.userId
    runtime["project_id"] = request.projectId
    runtime["python_version"] = request.pythonVersion
    runtime["container_name"] = result.get("container_name") or ""
    _set_runtime(workspace_abs, runtime)

    return {
        "status": result["status"],
        "message": result["message"],
        "containerName": result["container_name"],
        "image": result["image"],
    }

@app.post("/execute-command")
async def execute_command(request: ExecuteCommandRequest):
    result = _execute_command_in_container(
        user_id=request.userId,
        project_id=request.projectId,
        command=request.command,
        working_dir=request.workingDir,
    )
    return result

@app.post("/stop-project")
async def stop_project(request: StopProjectRequest):
    result = _stop_project_container(
        user_id=request.userId,
        project_id=request.projectId,
    )

    workspace_path = os.path.abspath(CURRENT_DIR) if CURRENT_DIR else None
    if workspace_path:
        runtime = _get_runtime(workspace_path)
        if runtime.get("user_id") == request.userId and runtime.get("project_id") == request.projectId:
            runtime["container_name"] = ""
            _set_runtime(workspace_path, runtime)

    return result

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
                code_context = payload.get("code_context", "")
                session.update_code_context(code_context)
                if not session._chat_session and session._line_buffer.strip().lower() != "chat":
                    await session.start_chat(code_context)
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
