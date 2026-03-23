
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from workspace_module1.main import app as m1
from workspace_module2.main import app as m2
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root level Mini IDE (Module 1)
app.mount("/", m1)
# Module 2 dashboard and endpoints
app.mount("/module2", m2)

if __name__ == "__main__":
    print("--------------------------------------------------")
    print("🚀 Mini IDE stable server is starting...")
    print("🔗 Link: http://localhost:8001/mini_ide")
    print("--------------------------------------------------")
    # Using programmatic start for maximum stability on Windows
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
