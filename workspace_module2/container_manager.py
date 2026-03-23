import os
import re
import subprocess
from typing import Optional, Dict, Any

DEFAULT_IMAGE = os.environ.get("WORKSPACE_CONTAINER_IMAGE", "python:3.12")
WORKSPACE_MOUNT_PATH = "/workspace"
CONTAINER_NAME_PREFIX = "ide"
WORKSPACE_DATA_ROOT = os.environ.get(
    "WORKSPACE_DATA_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace_data")),
)


def _run_command(command: list) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        error_msg = exc.stderr or exc.stdout or str(exc)
        lower_msg = error_msg.lower()
        if "connect" in lower_msg and "daemon" in lower_msg:
            raise RuntimeError(
                "Docker Desktop is not running. Please start Docker Desktop and wait a few seconds before trying again."
            )
        raise RuntimeError(f"Docker error: {error_msg}")


def _slug(value: str) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")


def _container_name(user_id: Optional[str], project_id: Optional[str]) -> str:
    user_part = _slug(user_id or "default")
    project_part = _slug(project_id or "default")
    return f"{CONTAINER_NAME_PREFIX}_{user_part}_{project_part}"


def _container_name_with_version(user_id: Optional[str], project_id: Optional[str], python_version: Optional[str]) -> str:
    user_part = _slug(user_id or "default")
    project_part = _slug(project_id or "default")
    version_part = _slug(python_version or "3.12")
    return f"{CONTAINER_NAME_PREFIX}_{user_part}_{project_part}_{version_part}"


def _image_for_version(python_version: Optional[str]) -> str:
    version = (python_version or "").strip()
    if version in ("3.10", "3.10.x", "3.10.0"):
        return "ide-python-3.10"
    if version in ("3.11", "3.11.x", "3.11.0"):
        return "ide-python-3.11"
    if version in ("3.12", "3.12.x", "3.12.0"):
        return "ide-python-3.12"
    if version:
        return f"ide-python-{version}"
    return "ide-python-3.12"


def _workspace_path(user_id: str, project_id: str) -> str:
    user_part = _slug(user_id or "default")
    project_part = _slug(project_id or "default")
    return os.path.abspath(os.path.join(WORKSPACE_DATA_ROOT, user_part, project_part))


def _docker_ready() -> None:
    _run_command(["docker", "info"])


def _container_exists(container_name: str) -> bool:
    inspect = subprocess.run(
        ["docker", "inspect", container_name],
        capture_output=True,
        text=True,
    )
    return inspect.returncode == 0


def _container_status(container_name: str) -> str:
    return _run_command(["docker", "inspect", "-f", "{{.State.Status}}", container_name])


def _container_id(container_name: str) -> str:
    return _run_command(["docker", "inspect", "-f", "{{.Id}}", container_name])


def get_or_create_container(user_id: str, project_id: str, python_version: Optional[str] = None) -> Dict[str, Any]:
    return start_container(user_id, project_id, python_version=python_version)


def start_container(user_id: str, project_id: str, python_version: Optional[str] = None) -> Dict[str, Any]:
    if not user_id or not project_id:
        raise RuntimeError("user_id and project_id are required")

    _docker_ready()

    host_path = _workspace_path(user_id, project_id)
    os.makedirs(host_path, exist_ok=True)
    image_to_use = _image_for_version(python_version)
    container_name = _container_name_with_version(user_id, project_id, python_version)

    print(f"[container_manager] container: {container_name}")
    print(f"[container_manager] workspace path: {host_path}")
    print(f"[container_manager] python_version: {python_version or '3.12'}")
    print(f"[container_manager] image: {image_to_use}")

    if _container_exists(container_name):
        status = _container_status(container_name)
        if status != "running":
            _run_command(["docker", "start", container_name])
        container_id = _container_id(container_name)
        print("[container_manager] reused: True")
        return {
            "status": "success",
            "container_id": container_id,
            "container_name": container_name,
            "workspace_path": host_path,
            "mount_path": WORKSPACE_MOUNT_PATH,
            "python_version": python_version or "3.12",
            "image": image_to_use,
            "reused": True,
        }

    command = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "-v",
        f"{host_path}:{WORKSPACE_MOUNT_PATH}",
        "-w",
        WORKSPACE_MOUNT_PATH,
        image_to_use,
        "sleep",
        "infinity",
    ]
    container_id = _run_command(command)
    print("[container_manager] reused: False")
    return {
        "status": "success",
        "container_id": container_id,
        "container_name": container_name,
        "workspace_path": host_path,
        "mount_path": WORKSPACE_MOUNT_PATH,
        "python_version": python_version or "3.12",
        "image": image_to_use,
        "reused": False,
    }


def start_or_reuse_container(
    workspace_id: str,
    workspace_path: str,
    student_id: Optional[str] = None,
    image: Optional[str] = None,
    python_version: Optional[str] = None,
) -> Dict[str, Any]:
    if not workspace_id or not workspace_path:
        raise RuntimeError("workspace_id and workspace_path are required")

    _docker_ready()

    host_path = os.path.abspath(workspace_path)
    os.makedirs(host_path, exist_ok=True)
    if image:
        image_to_use = image
    elif python_version:
        image_to_use = _image_for_version(python_version)
    else:
        image_to_use = DEFAULT_IMAGE

    container_name = _container_name(student_id, workspace_id)

    if _container_exists(container_name):
        status = _container_status(container_name)
        if status != "running":
            _run_command(["docker", "start", container_name])
        container_id = _container_id(container_name)
        return {
            "status": "success",
            "container_id": container_id,
            "container_name": container_name,
            "workspace_id": workspace_id,
            "mount_path": WORKSPACE_MOUNT_PATH,
            "reused": True,
        }

    command = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "-v",
        f"{host_path}:{WORKSPACE_MOUNT_PATH}",
        "-w",
        WORKSPACE_MOUNT_PATH,
        image_to_use,
        "sleep",
        "infinity",
    ]
    container_id = _run_command(command)
    return {
        "status": "success",
        "container_id": container_id,
        "container_name": container_name,
        "workspace_id": workspace_id,
        "mount_path": WORKSPACE_MOUNT_PATH,
        "reused": False,
    }


def start_or_reuse_container_for_path(
    workspace_path: str,
    user_id: str,
    project_id: str,
    python_version: Optional[str] = None,
) -> Dict[str, Any]:
    if not workspace_path:
        raise RuntimeError("workspace_path is required")
    if not user_id or not project_id:
        raise RuntimeError("user_id and project_id are required")

    _docker_ready()

    host_path = os.path.abspath(workspace_path)
    os.makedirs(host_path, exist_ok=True)
    image_to_use = _image_for_version(python_version)
    container_name = _container_name_with_version(user_id, project_id, python_version)

    if _container_exists(container_name):
        status = _container_status(container_name)
        if status != "running":
            _run_command(["docker", "start", container_name])
        container_id = _container_id(container_name)
        return {
            "status": "success",
            "container_id": container_id,
            "container_name": container_name,
            "workspace_path": host_path,
            "mount_path": WORKSPACE_MOUNT_PATH,
            "python_version": python_version or "3.12",
            "image": image_to_use,
            "reused": True,
        }

    command = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "-v",
        f"{host_path}:{WORKSPACE_MOUNT_PATH}",
        "-w",
        WORKSPACE_MOUNT_PATH,
        image_to_use,
        "sleep",
        "infinity",
    ]
    container_id = _run_command(command)
    return {
        "status": "success",
        "container_id": container_id,
        "container_name": container_name,
        "workspace_path": host_path,
        "mount_path": WORKSPACE_MOUNT_PATH,
        "python_version": python_version or "3.12",
        "image": image_to_use,
        "reused": False,
    }


def stop_container(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    student_id: Optional[str] = None,
    remove: bool = True,
) -> Dict[str, Any]:
    if user_id or project_id:
        if not user_id or not project_id:
            raise RuntimeError("user_id and project_id are required")
        container_name = _container_name(user_id, project_id)
    else:
        if not workspace_id:
            raise RuntimeError("workspace_id is required")
        container_name = _container_name(student_id, workspace_id)

    _docker_ready()

    if not _container_exists(container_name):
        raise RuntimeError("Container not found")

    _run_command(["docker", "stop", container_name])
    if remove:
        _run_command(["docker", "rm", container_name])

    return {
        "status": "success",
        "container_name": container_name,
        "removed": remove,
    }
