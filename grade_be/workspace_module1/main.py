from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import shutil
import subprocess
import sys
from typing import List, Optional, Dict, Any
# import tkinter as tk (Moved to local scope)
# from tkinter import filedialog (Moved to local scope)

app = FastAPI()

# Global state
CURRENT_DIR: Optional[str] = None
DOCKER_HOST_ROOT: str = r"C:\ip_docker"

# Local dictionary to track if container is being started
IS_CONTAINER_READY: Dict[str, bool] = {}

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
    if not request.path:
        # User requested projects to be under the Docker Root
        os.makedirs(DOCKER_HOST_ROOT, exist_ok=True)
        request.path = os.path.join(DOCKER_HOST_ROOT, request.name or "NewProject")

    target_path = os.path.abspath(os.path.expanduser(request.path))
    try:
        os.makedirs(target_path, exist_ok=True)
        CURRENT_DIR = target_path
        return {"current_dir": CURRENT_DIR, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/list_files")
async def list_files():
    """Returns the hierarchical file tree for the active workspace."""
    if not CURRENT_DIR:
        return {"files": [], "current_dir": None, "status": "no_workspace"}

    def build_tree(base_path):
        nodes = []
        try:
            items = sorted(os.listdir(base_path), key=lambda x: (not os.path.isdir(os.path.join(base_path, x)), x.lower()))
            for item in items:
                path = os.path.join(base_path, item)
                rel_path = os.path.relpath(path, CURRENT_DIR).replace("\\", "/")
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

    return {"files": build_tree(CURRENT_DIR), "current_dir": CURRENT_DIR, "status": "success"}

@app.post("/create_item")
async def create_item(request: CreateItemRequest):
    """Creates a new file or folder inside the active workspace."""
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    try:
        target_path = os.path.join(CURRENT_DIR, request.name)
        if os.path.exists(target_path):
            raise HTTPException(status_code=400, detail="Item already exists")
        
        if request.type == "folder":
            os.makedirs(target_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                pass
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/delete_item")
async def delete_item(request: PathRequest):
    """Deletes a file or folder from the workspace."""
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    target_rel_path = request.path or request.name
    if not target_rel_path:
        raise HTTPException(status_code=400, detail="Path or Name is required")
    
    try:
        target_path = os.path.join(CURRENT_DIR, target_rel_path)
        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail="Item not found")
        
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save_file")
async def save_file(request: SaveFileRequest):
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    try:
        path = os.path.join(CURRENT_DIR, request.file_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(request.code_content)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/view_file")
async def view_file(file_name: str):
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    try:
        path = os.path.join(CURRENT_DIR, file_name)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"code_content": content, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run_file")
async def run_file(request: RunFileRequest):
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    try:
        file_path = os.path.join(CURRENT_DIR, request.file_name)
        # We ensure stdin is passed to the process
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.run(
            [sys.executable, file_path],
            cwd=CURRENT_DIR,
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
