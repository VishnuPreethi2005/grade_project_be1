from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
from typing import Dict, Optional

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from workspace_module2.container_manager import (
    start_or_reuse_container,
    stop_container as cm_stop_container,
    WORKSPACE_MOUNT_PATH,
)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="workspace_module2/static"), name="static")

@app.get("/module2/dashboard")
async def get_dashboard():
    return FileResponse("workspace_module2/static/index.html")

# Global dictionary to store container IDs: {project_name: container_id}
containers_db: Dict[str, str] = {}

class StartRequest(BaseModel):
    project_name: str
    host_path: str

class StopRequest(BaseModel):
    project_name: str

class ContainerStartRequest(BaseModel):
    workspace_id: str
    workspace_path: str
    student_id: Optional[str] = None
    image: Optional[str] = None

class ContainerStopRequest(BaseModel):
    workspace_id: str
    student_id: Optional[str] = None
    remove: bool = True

def run_command(command: list):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr or e.stdout or str(e)
        if "connect" in error_msg.lower() and "daemon" in error_msg.lower():
            raise HTTPException(
                status_code=503, 
                detail="Docker Desktop is not running. Please start Docker Desktop and wait a few seconds before trying again."
            )
        raise HTTPException(status_code=500, detail=f"Docker error: {error_msg}")


@app.post("/module2/start")
async def start_container(request: StartRequest):
    project_name = request.project_name
    container_name = f"{project_name}_container"
    host_path = os.path.abspath(request.host_path)

    # 1. Check if container already exists
    try:
        inspect = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True,
            text=True
        )
        if inspect.returncode == 0:
            # If exists but stopped, start it
            run_command(["docker", "start", container_name])
            return {"status": "success", "message": f"Container {container_name} resumed.", "project": project_name}
    except Exception:
        pass

    # 2. Create and Run new container
    # -d: detached
    # --name: format requested
    # -v: host folder to /workspace
    # command: sleep infinity
    command = [
        "docker", "run", "-d",
        "--name", container_name,
        "-v", f"{host_path}:/workspace",
        "python:3.12-slim",
        "sleep", "infinity"
    ]
    
    container_id = run_command(command)
    containers_db[降低case(project_name)] = container_id
    
    return {
        "status": "success",
        "container_id": container_id,
        "container_name": container_name,
        "mount_path": "/workspace",
        "project": project_name
    }

@app.post("/module2/containers/start")
async def start_workspace_container(request: ContainerStartRequest):
    try:
        return start_or_reuse_container(
            workspace_id=request.workspace_id,
            workspace_path=request.workspace_path,
            student_id=request.student_id,
            image=request.image,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Docker Desktop is not running" in msg:
            raise HTTPException(status_code=503, detail=msg)
        if "required" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

@app.post("/module2/stop")
async def stop_container(request: StopRequest):
    container_name = f"{request.project_name}_container"
    try:
        run_command(["docker", "stop", container_name])
        return {"status": "success", "message": f"Container {container_name} stopped."}
    except HTTPException as e:
        if "No such container" in str(e.detail):
             raise HTTPException(status_code=404, detail="Container not found")
        raise e

@app.post("/module2/containers/stop")
async def stop_workspace_container(request: ContainerStopRequest):
    try:
        return cm_stop_container(
            workspace_id=request.workspace_id,
            student_id=request.student_id,
            remove=request.remove,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Docker Desktop is not running" in msg:
            raise HTTPException(status_code=503, detail=msg)
        if "required" in msg:
            raise HTTPException(status_code=400, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

@app.get("/module2/status/{project_name}")
async def get_status(project_name: str):
    container_name = f"{project_name}_container"
    try:
        status = run_command(["docker", "inspect", "-f", "{{.State.Status}}", container_name])
        return {"project": project_name, "container_name": container_name, "status": status}
    except Exception:
        return {"project": project_name, "container_name": container_name, "status": "not_created"}

def 降低case(s: str):
    return s.lower().replace(" ", "_")
