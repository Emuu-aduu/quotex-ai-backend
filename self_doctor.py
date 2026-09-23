import time
import requests
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# .env ফাইল লোড করা
load_dotenv()

PRIMARY_HEALTH_URL = os.getenv("BACKEND_HEALTH_URL", "http://127.0.0.1:8000/health")
FALLBACK_HEALTH_URL = os.getenv("BACKEND_FALLBACK_URL", "http://127.0.0.1:8000/")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))
LOG_FILE = "self_doctor.log"

logger = logging.getLogger("SelfDoctor")
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

# উইন্ডোজ টার্মিনালের এনকোডিং ক্র্যাশ এড়াতে UTF-8 এনকোডিং ফোর্স করা
console_handler = logging.StreamHandler(sys.stdout)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

console_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")
console_handler.setFormatter(console_formatter)

if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

session = requests.Session()

def check_backend_health():
    try:
        response = session.get(PRIMARY_HEALTH_URL, timeout=5)
        if response.status_code == 200:
            logger.info("Backend is HEALTHY and responsive.")
            return True
        elif response.status_code == 404:
            fallback_response = session.get(FALLBACK_HEALTH_URL, timeout=5)
            if fallback_response.status_code == 200:
                logger.warning("Warning: '/health' endpoint not found (404), but server root '/' is responding.")
                return True
            else:
                logger.error(f"ERROR: Fallback URL failed with status code {fallback_response.status_code}")
                return False
        
        logger.warning(f"Warning: Backend responded with status code {response.status_code}")
        return False

    except requests.exceptions.ConnectionError:
        logger.error(f"CRITICAL ALERT: Backend server is DOWN at {PRIMARY_HEALTH_URL}!")
        return False
    except Exception as e:
        logger.error(f"ERROR: Unexpected exception occurred: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info(f"Self Doctor Monitoring System Started... Target: {PRIMARY_HEALTH_URL}")
    
    try:
        while True:
            check_backend_health()
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Self Doctor stopped gracefully by user.")
        sys.exit(0)