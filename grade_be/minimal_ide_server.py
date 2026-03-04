
from fastapi import FastAPI
from workspace_module1.main import app as m1
from workspace_module2.main import app as m2
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount or Route
# In module1, it has routes like /mini_ide, /list_files, etc.
# In module2, it has routes starting with /module2

# We can use a combined application or mount them
# Since they are both FastAPI, we can just include their routers or mount them if they use prefixes
# But asgi.py approach was simpler. Let's do a simple ASGI dispatcher if we want to mimic it,
# or just mount them as sub-apps.

app.mount("/", m1)
app.mount("/module2", m2)

if __name__ == "__main__":
    print("Starting Combined Mini IDE Server on http://localhost:8000/mini_ide")
    uvicorn.run(app, host="127.0.0.1", port=8000)
