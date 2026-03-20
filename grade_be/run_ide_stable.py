
import uvicorn
from workspace_module1.main import app

if __name__ == "__main__":
    print("Starting Mini IDE (Module 1) on http://localhost:8001/mini_ide")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
