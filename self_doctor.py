import os
import sys
import time
import signal
import logging
from logging.handlers import RotatingFileHandler
import requests

# ---------------------------------------------------------
# 1. Safe Parser for Environment Variables
# ---------------------------------------------------------
def safe_int_env(key: str, default: int) -> int:
    """Environment variable safe integer conversion with fallback."""
    raw_val = os.getenv(key)
    if not raw_val:
        return default
    try:
        clean_val = str(raw_val).strip()
        return int(clean_val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------
# 2. Dynamic Config Import & Initialization
# ---------------------------------------------------------
try:
    from config import settings
    DEFAULT_HOST = "127.0.0.1" if settings.HOST == "0.0.0.0" else settings.HOST
    DEFAULT_PORT = settings.PORT
    ENV_MODE = getattr(settings, "ENV", "development")
except ImportError:
    settings = None
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8000
    ENV_MODE = "unknown"

PRIMARY_HEALTH_URL = os.getenv("BACKEND_HEALTH_URL", f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health")
FALLBACK_HEALTH_URL = os.getenv("BACKEND_FALLBACK_URL", f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/")
CHECK_INTERVAL = safe_int_env("CHECK_INTERVAL", 30)
LOG_FILE = "self_doctor.log"

# ---------------------------------------------------------
# 3. Logger Setup
# ---------------------------------------------------------
logger = logging.getLogger("SelfDoctor")
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler(sys.stdout)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

console_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")
console_handler.setFormatter(console_formatter)

if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

session = requests.Session()

# Stop Flag for Graceful Shutdown
keep_running = True


def handle_shutdown_signal(signum, frame):
    global keep_running
    logger.info("Shutdown signal received. Stopping Self Doctor cleanly...")
    keep_running = False


signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)


# ---------------------------------------------------------
# 4. Signal Engine Component Diagnostics
# ---------------------------------------------------------
def check_internal_signal_engine() -> dict:
    """
    Checks signal engine dependencies: DuckDB storage and Cache availability.
    """
    results = {"duckdb": False, "cache": False}

    # DuckDB Test
    test_db_file = "doctor_temp_test.duckdb"
    try:
        from db_store import DuckDBStorageEngine
        db = DuckDBStorageEngine(test_db_file)
        db.close()
        if os.path.exists(test_db_file):
            os.remove(test_db_file)
        results["duckdb"] = True
    except Exception as err:
        logger.error(f"[DIAGNOSTIC] DuckDB Engine Check Failed: {err}")

    # Cache Engine Test
    try:
        from cache_manager import HybridCacheManager
        cache = HybridCacheManager()
        cache.set("doctor_ping", "pong", ttl_seconds=5)
        if cache.get("doctor_ping") == "pong":
            results["cache"] = True
    except Exception as err:
        logger.error(f"[DIAGNOSTIC] Hybrid Cache Engine Check Failed: {err}")

    return results


# ---------------------------------------------------------
# 5. HTTP Endpoint Health Verification
# ---------------------------------------------------------
def check_backend_health() -> bool:
    """Pings server health endpoint and verifies HTTP responsiveness."""
    try:
        response = session.get(PRIMARY_HEALTH_URL, timeout=5)
        if response.status_code == 200:
            logger.info("Backend HTTP Endpoint is HEALTHY and responsive.")
            return True
        elif response.status_code == 404:
            fallback_response = session.get(FALLBACK_HEALTH_URL, timeout=5)
            if fallback_response.status_code == 200:
                logger.warning("Warning: '/health' endpoint not found (404), but root '/' is responding.")
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


# ---------------------------------------------------------
# 6. Main Runner
# ---------------------------------------------------------
def run_diagnostics_and_monitor(once_only: bool = False):
    logger.info(f"Self Doctor Diagnostic System Started (Mode: {ENV_MODE})")
    
    # Run Signal Engine Components Diagnostic
    components = check_internal_signal_engine()
    logger.info(f"[SIGNAL ENGINE HEALTH] DuckDB: {'OK' if components['duckdb'] else 'FAIL'} | Cache: {'OK' if components['cache'] else 'FAIL'}")

    if once_only:
        check_backend_health()
        return

    # Monitoring Loop with graceful sleep interval check
    while keep_running:
        check_backend_health()
        for _ in range(CHECK_INTERVAL):
            if not keep_running:
                break
            time.sleep(1)


if __name__ == "__main__":
    # Param argument `--once` allows single-shot diagnostic without infinite loop
    is_once = "--once" in sys.argv
    run_diagnostics_and_monitor(once_only=is_once)