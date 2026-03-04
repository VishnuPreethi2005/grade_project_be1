from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import shutil
import subprocess
import sys
from typing import List, Optional, Dict, Any
import tkinter as tk
from tkinter import filedialog

app = FastAPI()

# Global state to track current workspace
CURRENT_DIR: Optional[str] = None

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
    """Triggers a real Windows folder selection dialog."""
    global CURRENT_DIR
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    selected_path = filedialog.askdirectory(title="Select Folder to Open in Mini IDE")
    root.destroy()
    
    if selected_path:
        CURRENT_DIR = os.path.abspath(selected_path)
        return {"current_dir": CURRENT_DIR, "status": "success"}
    return {"status": "cancelled"}

@app.post("/create_folder_workspace")
async def create_folder_workspace(request: PathRequest):
    """Creates a new folder on the system and sets it as the workspace."""
    global CURRENT_DIR
    if not request.path:
        # Default to a "Projects" directory near the backend if no absolute path provided
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects")
        os.makedirs(base, exist_ok=True)
        request.path = os.path.join(base, request.name or "NewProject")

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
            # Folders first, then alphabetical
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
    """Executes the Python file and captures output/errors."""
    if not CURRENT_DIR:
        raise HTTPException(status_code=400, detail="No workspace opened")
    try:
        file_path = os.path.join(CURRENT_DIR, request.file_name)
        process = subprocess.run(
            [sys.executable, file_path],
            cwd=CURRENT_DIR,
            input=request.stdin_input if request.stdin_input else None,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "stdout": process.stdout,
            "stderr": process.stderr,
            "returncode": process.returncode,
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/mini_ide")
async def mini_ide():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))
