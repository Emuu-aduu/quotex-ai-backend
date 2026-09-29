import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import os
import time
from typing import Any, Dict, Literal, Optional
import uuid

from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Security,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
import uvicorn

# 1. Environment Variables - Always load FIRST
load_dotenv()

# Structured Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
)
logger = logging.getLogger("quotex_signal_system")

# Custom Module Imports
from live_fetcher import LiveFetcher
from strategy_engine import StrategyEngine
from trust_engine import TrustEngine

# Global Environment Variables
IS_DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_OWNER = os.getenv("REPO_OWNER", "")
REPO_NAME = os.getenv("REPO_NAME", "")
QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL", "")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD", "")

# Safe Singleton Initialization (Prevents Server Crash if Fetcher Fails initially)
try:
    live_fetcher = LiveFetcher()
except Exception as init_err:
    logger.error(f"LiveFetcher initialization error: {init_err}")
    live_fetcher = None

strategy_engine = StrategyEngine(fetcher=live_fetcher)
trust_engine = TrustEngine(
    github_token=GITHUB_TOKEN, repo_owner=REPO_OWNER, repo_name=REPO_NAME
)


# FastAPI Lifespan Context Manager (Modern Startup & Shutdown Handling)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Quotex AI Signal System Backend...")

    # Validate mandatory environment variables
    if not all([GITHUB_TOKEN, REPO_OWNER, REPO_NAME]):
        err_msg = "Critical Error: GitHub configurations are missing in environment variables!"
        if not IS_DEBUG:
            logger.critical(err_msg)
        else:
            logger.warning(err_msg)

    if not all([QUOTEX_EMAIL, QUOTEX_PASSWORD]):
        logger.warning(
            "WARNING: QUOTEX_EMAIL or QUOTEX_PASSWORD is not set in environment variables."
        )

    yield

    logger.info("Shutting down Quotex AI Signal System Backend...")
    # Clean up connections if applicable
    if live_fetcher and hasattr(live_fetcher, "close"):
        try:
            if asyncio.iscoroutinefunction(live_fetcher.close):
                await live_fetcher.close()
            else:
                live_fetcher.close()
        except Exception as close_err:
            logger.warning(f"Error during LiveFetcher closure: {close_err}")


app = FastAPI(
    title="Quotex AI Signal System",
    description="Enterprise API with Passkey Protection & Automated GitHub Persistence",
    version="2.0.0",
    lifespan=lifespan,
)

# API Key Security Setup
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    expected_key = os.getenv("API_KEY", "")

    if not expected_key:
        if not IS_DEBUG:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server configuration error: API_KEY environment variable is not set.",
            )
        return api_key

    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing X-API-Key header.",
        )
    return api_key


# Dynamic CORS Policy Configuration
if IS_DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )
else:
    raw_origins = os.getenv("ALLOWED_ORIGINS", "")
    allowed_origins = [
        origin.strip() for origin in raw_origins.split(",") if origin.strip()
    ]

    if not allowed_origins:
        logger.warning(
            "WARNING: ALLOWED_ORIGINS is empty in production! Defaulting to strict secure restrictions."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )


# Pydantic Response Schemas
class RootResponse(BaseModel):
    status: str = Field(..., examples=["online"])
    message: str = Field(..., examples=["Quotex AI Signal Server is Running"])


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["healthy"])
    service: str = Field(..., examples=["Quotex AI Signal Backend"])
    timestamp: str = Field(..., examples=["2026-09-29 21:30:00"])


class SignalResponse(BaseModel):
    status: str = Field(..., examples=["SUCCESS"])
    id: Optional[str] = Field(None, examples=["SIG-1727616600-A1B2"])
    asset: Optional[str] = Field(None, examples=["EUR/USD"])
    direction: Optional[str] = Field(None, examples=["CALL"])
    score: Optional[str] = Field(None, examples=["8/10"])
    percentage: Optional[str] = Field(None, examples=["80.0%"])
    timeframe: Optional[str] = Field(None, examples=["1m"])
    timestamp: Optional[str] = Field(None, examples=["2026-09-29 21:30:00"])
    hash: Optional[str] = Field(None, examples=["a1b2c3d4..."])
    github_status: Optional[str] = Field(None, examples=["QUEUED"])
    message: Optional[str] = Field(
        None, examples=["65%+ confirmation pawa jayni"]
    )


def parse_score_to_percentage(score_val: Any) -> float:
    """Safely converts scores ('8/10', '80%', 0.8, 80) into a clean percentage float (0.0 to 100.0)."""
    try:
        if isinstance(score_val, (int, float)):
            val = float(score_val)
            return val * 100.0 if val <= 1.0 else val

        if isinstance(score_val, str):
            clean_str = score_val.strip().replace("%", "")
            if "/" in clean_str:
                parts = clean_str.split("/")
                if len(parts) == 2:
                    num, den = float(parts[0]), float(parts[1])
                    if den > 0:
                        return (num / den) * 100.0
            else:
                val = float(clean_str)
                return val * 100.0 if val <= 1.0 else val
    except (ValueError, TypeError, ZeroDivisionError) as err:
        logger.warning(f"Score parsing failed for value '{score_val}': {err}")
    except Exception as err:
        logger.error(f"Unexpected error in score parsing: {err}", exc_info=True)
    return 0.0


async def async_github_commit(signal_data: Dict[str, Any], signal_hash: str):
    """Executes blocking GitHub commits asynchronously with retry backoff."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = await asyncio.to_thread(
                trust_engine.commit_to_github, signal_data, signal_hash
            )
            logger.info(
                f"Signal {signal_data.get('id')} committed to GitHub successfully: {url}"
            )
            return
        except Exception as err:
            logger.warning(
                f"GitHub commit attempt {attempt + 1} failed for {signal_data.get('id')}: {err}"
            )
            if attempt == max_retries - 1:
                logger.error(
                    f"All retry attempts failed for GitHub commit: {signal_data.get('id')}"
                )
            else:
                await asyncio.sleep(2 * (attempt + 1))


@app.get("/", response_model=RootResponse)
def root():
    return RootResponse(
        status="online", message="Quotex AI Signal Server is Running"
    )


@app.get("/health", response_model=HealthResponse, tags=["Health Check"])
async def health_check():
    return HealthResponse(
        status="healthy",
        service="Quotex AI Signal Backend",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.get(
    "/api/v1/get-signal",
    response_model=SignalResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_on_demand_signal(
    background_tasks: BackgroundTasks,
    timeframe: Literal["1m", "5m", "10m", "15m", "30m", "1hr"] = "1m",
):
    try:
        # Check connection status safely without throwing AttributeError
        if not live_fetcher or not getattr(live_fetcher, "is_connected", False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API DISCONNECTED: Market fetcher is currently offline or re-authenticating.",
            )

        live_scan = await strategy_engine.scan_best_stable_market(
            timeframe=timeframe
        )

        if (
            not live_scan
            or live_scan.get("action") == "HOLD"
            or live_scan.get("status") != "SIGNAL"
        ):
            reason_msg = (
                live_scan.get("reason", "65%+ confirmation pawa jayni")
                if live_scan
                else "No market data found"
            )
            return SignalResponse(
                status="NO_SIGNAL", timeframe=timeframe, message=reason_msg
            )

        symbol = (
            live_scan.get("symbol") or live_scan.get("pair") or "EUR/USD"
        )
        raw_score = live_scan.get("score", "0/10")
        direction = (
            live_scan.get("direction") or live_scan.get("action") or "HOLD"
        )

        score_percentage = parse_score_to_percentage(raw_score)

        if score_percentage < 65.0 or direction in ["NO_SIGNAL", "HOLD"]:
            logger.info(
                f"Signal confirmation failed for {symbol}. Score: {score_percentage:.1f}%"
            )
            return SignalResponse(
                status="NO_SIGNAL",
                timeframe=timeframe,
                message=(
                    f"65%+ confirmation pawa jayni (Current Score: {raw_score} / {score_percentage:.1f}%)"
                ),
            )

        signal_id = f"SIG-{int(time.time())}-{uuid.uuid4().hex[:4].upper()}"
        signal_data = {
            "id": signal_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "asset": symbol,
            "direction": direction,
            "score": str(raw_score),
            "timeframe": timeframe,
        }

        signal_hash = trust_engine.generate_signal_hash(signal_data)
        background_tasks.add_task(
            async_github_commit, signal_data, signal_hash
        )

        logger.info(
            f"Signal generated successfully: {signal_id} ({symbol}) for {timeframe}"
        )

        return SignalResponse(
            status="SUCCESS",
            id=signal_data["id"],
            asset=signal_data["asset"],
            direction=signal_data["direction"],
            score=signal_data["score"],
            percentage=f"{score_percentage:.1f}%",
            timeframe=timeframe,
            timestamp=signal_data["timestamp"],
            hash=signal_hash,
            github_status="QUEUED",
        )

    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Unhandled Engine Error: {err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Engine Error: {str(err)}",
        )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=IS_DEBUG)