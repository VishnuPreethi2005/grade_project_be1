import logging
import sys
from pathlib import Path
# from icecream import ic

def configure_logging():
    logs_dir = Path(__file__).parent.parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(logs_dir / 'app.log'),
            #logging.StreamHandler(sys.stdout)
        ]
    )
    # ic.configureOutput(includeContext=True)

logger = logging.getLogger(__name__)
