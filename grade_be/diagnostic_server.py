
from fastapi import FastAPI
from workspace_module1.main import app as m1
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

# Configure logging to file
logging.basicConfig(
    filename='server_diagnostic.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s'
)

app = FastAPI()

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/", m1)

if __name__ == "__main__":
    logging.info("Starting Minimal IDE Server on port 8001")
    print("Serving on http://localhost:8001/mini_ide")
    try:
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="debug")
    except Exception as e:
        logging.exception("Server crashed with exception")
