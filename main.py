import os
import time
import uuid
import logging
import asyncio
from datetime import datetime  # <--- datetime মডিউল ইম্পোর্ট করা হলো
from typing import Dict, Any, Optional, Literal
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# .env file load kora
load_dotenv()

# Structured Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("quotex_signal_system")

from strategy_engine import StrategyEngine
from trust_engine import TrustEngine

app = FastAPI(title="Quotex AI Signal System")

# 1. DEBUG default 'false' for production safety
IS_DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")

# 2. CORS Setup with Empty ALLOWED_ORIGINS safety fallback
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
    allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    
    # Safe fallback if ALLOWED_ORIGINS is accidentally left empty in production
    if not allowed_origins:
        logger.warning("WARNING: ALLOWED_ORIGINS is empty in production! Defaulting to strict secure restrictions.")
        allowed_origins = []

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )

# ENV Validation: Production e token missing thakle app start hobei na
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_OWNER = os.getenv("REPO_OWNER", "")
REPO_NAME = os.getenv("REPO_NAME", "")

if not all([GITHUB_TOKEN, REPO_OWNER, REPO_NAME]):
    error_msg = "Critical Error: GitHub configurations are missing in environment variables!"
    if not IS_DEBUG:
        raise RuntimeError(error_msg)
    else:
        logger.warning(error_msg)

strategy_engine = StrategyEngine()
trust_engine = TrustEngine(
    github_token=GITHUB_TOKEN,
    repo_owner=REPO_OWNER,
    repo_name=REPO_NAME
)

# Pydantic Schemas
class RootResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"examples": ["online"]})
    message: str = Field(..., json_schema_extra={"examples": ["Quotex AI Signal Server is Running"]})

# হেলথ চেক রেসপন্স মডেল
class HealthResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"examples": ["healthy"]})
    service: str = Field(..., json_schema_extra={"examples": ["Quotex AI Signal Backend"]})
    timestamp: str = Field(..., json_schema_extra={"examples": ["2026-09-22 22:55:00"]})

class SignalResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"examples": ["SUCCESS"]})
    id: Optional[str] = Field(None, json_schema_extra={"examples": ["SIG-1695200000-A1B2"]})
    asset: Optional[str] = Field(None, json_schema_extra={"examples": ["EUR/USD"]})
    direction: Optional[str] = Field(None, json_schema_extra={"examples": ["UP"]})
    score: Optional[str] = Field(None, json_schema_extra={"examples": ["8/9"]})
    percentage: Optional[str] = Field(None, json_schema_extra={"examples": ["88.9%"]})
    timeframe: Optional[str] = Field(None, json_schema_extra={"examples": ["1m"]})
    timestamp: Optional[str] = Field(None, json_schema_extra={"examples": ["2026-09-21 18:47:00"]})
    hash: Optional[str] = Field(None, json_schema_extra={"examples": ["a1b2c3d4..."]})
    github_status: Optional[str] = Field(None, json_schema_extra={"examples": ["QUEUED"]})
    message: Optional[str] = Field(None, json_schema_extra={"examples": ["75%+ confirmation pawa jayni"]})


def parse_score_to_percentage(score_val: Any) -> float:
    try:
        if isinstance(score_val, (int, float)):
            return float(score_val)
        
        if isinstance(score_val, str) and "/" in score_val:
            parts = score_val.split("/")
            if len(parts) == 2:
                num, den = float(parts[0]), float(parts[1])
                if den > 0:
                    return (num / den) * 100.0
    except (ValueError, TypeError, ZeroDivisionError) as err:
        logger.warning(f"Score parsing failed for value '{score_val}': {err}")
    except Exception as err:
        logger.error(f"Unexpected error in score parsing: {err}", exc_info=True)
    return 0.0


# GitHub Commit with Retry Mechanism
async def async_github_commit(signal_data: Dict[str, Any], signal_hash: str):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = await asyncio.to_thread(trust_engine.commit_to_github, signal_data, signal_hash)
            logger.info(f"Signal {signal_data.get('id')} committed to GitHub successfully: {url}")
            return
        except Exception as err:
            logger.warning(f"GitHub commit attempt {attempt + 1} failed for {signal_data.get('id')}: {err}")
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} retry attempts failed for GitHub commit: {signal_data.get('id')}")
            else:
                await asyncio.sleep(2 * (attempt + 1))


@app.get("/", response_model=RootResponse)
def root():
    return RootResponse(
        status="online",
        message="Quotex AI Signal Server is Running"
    )


@app.get("/health", response_model=HealthResponse, tags=["Health Check"])
async def health_check():
    return HealthResponse(
        status="healthy",
        service="Quotex AI Signal Backend",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.get("/api/v1/get-signal", response_model=SignalResponse)
async def get_on_demand_signal(
    background_tasks: BackgroundTasks,
    timeframe: Literal["1m", "5m", "10m", "15m", "30m", "1hr"] = "1m",
    x_api_key: Optional[str] = Header(None)
):
    expected_api_key = os.getenv("API_KEY", "")
    if expected_api_key and x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing API Key")

    try:
        live_scan = await asyncio.to_thread(strategy_engine.scan_best_stable_market)
        
        if not live_scan or live_scan.get("action") == "HOLD" or live_scan.get("status") != "SIGNAL":
            reason_msg = live_scan.get("reason", "75%+ confirmation pawa jayni") if live_scan else "No market data found"
            return SignalResponse(
                status="NO_SIGNAL",
                timeframe=timeframe,
                message=reason_msg
            )

        symbol = live_scan.get("symbol") or live_scan.get("pair") or "EUR/USD"
        raw_score = live_scan.get("score", "0/9")
        direction = live_scan.get("direction") or live_scan.get("action") or "HOLD"

        score_percentage = parse_score_to_percentage(raw_score)

        if score_percentage < 75.0 or direction in ["NO_SIGNAL", "HOLD"]:
            logger.info(f"Signal confirmation failed for {symbol}. Score: {score_percentage:.1f}%")
            return SignalResponse(
                status="NO_SIGNAL",
                timeframe=timeframe,
                message=f"75%+ confirmation pawa jayni (Current Score: {raw_score} / {score_percentage:.1f}%)"
            )

        signal_id = f"SIG-{int(time.time())}-{uuid.uuid4().hex[:4].upper()}"
        signal_data = {
            "id": signal_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "asset": symbol,
            "direction": direction,
            "score": str(raw_score),
            "timeframe": timeframe
        }

        signal_hash = trust_engine.generate_signal_hash(signal_data)

        background_tasks.add_task(async_github_commit, signal_data, signal_hash)

        logger.info(f"Signal generated successfully: {signal_id} ({symbol}) for {timeframe}")

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
            github_status="QUEUED"
        )

    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Unhandled Engine Error: {err}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Engine Error: {str(err)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=IS_DEBUG)