import os
import sys
import hashlib
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import flet as ft
import flet.fastapi as flet_fastapi

from config import settings
from db_store import DuckDBStorageEngine
from cache_manager import HybridCacheManager
from fcm_delivery import FCMDeliveryService

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MainSignalEngine")

# Initialize Storage & Cache Core Engines
db = DuckDBStorageEngine("signals_store.duckdb")
cache = HybridCacheManager()
fcm = FCMDeliveryService()

# Thread-Safe Shared Active Web UI Callbacks
ui_clients = set()
ui_clients_lock = threading.Lock()

# FastAPI Initialization
app = FastAPI(title="TradingView Signal Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root access directly to Flet Dashboard."""
    return RedirectResponse(url="/dashboard")


@app.get("/health")
def health_check():
    """Health status check endpoint for SelfDoctor and Uptime Monitors."""
    return {
        "status": "healthy",
        "environment": settings.ENV,
        "timestamp": datetime.utcnow().isoformat()
    }


def process_incoming_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Core Signal Pipeline: Deduplication, Persistence, Notification, and UI Broadcast."""
    symbol = str(payload.get("symbol", "UNKNOWN")).upper().strip()
    action = str(payload.get("action", "BUY")).upper().strip()
    timeframe = str(payload.get("timeframe", settings.DEFAULT_TIMEFRAME)).strip()

    try:
        price = float(payload.get("price", 0.0))
    except (ValueError, TypeError):
        price = 0.0

    # OTC Asset Handling / Standardization
    if "_OTC" in symbol or "OTC" in symbol:
        if not settings.ALLOW_OTC:
            logger.warning(f"OTC signal ignored due to configuration settings: {symbol}")
            return {"status": "ignored", "reason": "OTC_disabled"}

    # Signal Deduplication Check
    sig_raw_str = f"{symbol}_{action}_{timeframe}_{price}"
    sig_hash = hashlib.sha256(sig_raw_str.encode()).hexdigest()

    if cache.is_duplicate_signal(sig_hash):
        logger.warning(f"Duplicate signal detected and dropped: {symbol} {action}")
        return {"status": "duplicate", "hash": sig_hash}

    # Mark as processed in Cache (TTL 60 sec)
    cache.mark_signal_processed(sig_hash, ttl_seconds=60)

    signal_data = {
        "signal_id": sig_hash[:12],
        "symbol": symbol,
        "action": action,
        "timeframe": timeframe,
        "price": price,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Save to DuckDB Storage
    db.save_signal(signal_data)

    # FCM Mobile/Browser Push (Non-blocking)
    fcm.send_signal_notification(
        title=f"NEW SIGNAL: {symbol} {action}",
        body=f"Price: {price} | TF: {timeframe}",
        data=signal_data
    )

    # Thread-Safe Real-time Broadcast to Active Flet UI Clients
    with ui_clients_lock:
        active_callbacks = list(ui_clients)

    for client_callback in active_callbacks:
        try:
            client_callback(signal_data)
        except Exception as err:
            logger.error(f"Error broadcasting signal to UI client: {err}")

    logger.info(f"Signal Processed Successfully: {symbol} [{action}] @ {price}")
    return {"status": "success", "signal": signal_data}


@app.post("/webhook")
async def receive_webhook(request: Request):
    """TradingView Signal Webhook Receiver."""
    # Webhook Secret Authentication Check
    secret = request.headers.get("X-Webhook-Secret") or request.query_params.get("secret")
    if settings.WEBHOOK_SECRET and secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid Webhook Secret")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    result = process_incoming_signal(payload)
    return result


# Flet Dashboard UI Component
def main_ui(page: ft.Page):
    page.title = "TradingView Signal Dashboard"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.spacing = 15

    signals_list = ft.ListView(expand=True, spacing=10, padding=10)

    def build_signal_card(sig: dict):
        is_buy = sig.get("action") == "BUY"
        color = ft.colors.GREEN_400 if is_buy else ft.colors.RED_400
        return ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column([
                            ft.Text(f"{sig.get('symbol')} ({sig.get('timeframe')})", size=16, weight=ft.FontWeight.BOLD),
                            ft.Text(f"Time: {sig.get('timestamp')}", size=12, color=ft.colors.GREY_400),
                        ]),
                        ft.Text(f"{sig.get('action')}", size=18, weight=ft.FontWeight.BOLD, color=color),
                        ft.Text(f"Price: {sig.get('price')}", size=16, weight=ft.FontWeight.W_500),
                    ]
                )
            )
        )

    # Load Signal History from DuckDB
    recent_signals = db.get_recent_signals(limit=20)
    for sig in recent_signals:
        signals_list.controls.append(build_signal_card(sig))

    def on_new_signal(sig: dict):
        signals_list.controls.insert(0, build_signal_card(sig))
        page.update()

    # Thread-Safe UI Client Registration
    with ui_clients_lock:
        ui_clients.add(on_new_signal)

    def on_disconnect(e):
        with ui_clients_lock:
            ui_clients.discard(on_new_signal)

    page.on_disconnect = on_disconnect

    page.add(
        ft.Row([
            ft.Text("TradingView Live Signal Engine", size=22, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_400),
            ft.Container(
                content=ft.Text("ONLINE", size=12, color=ft.colors.GREEN_400, weight=ft.FontWeight.BOLD),
                border=ft.border.all(1, ft.colors.GREEN_400),
                border_radius=5,
                padding=5
            )
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Divider(height=1, color=ft.colors.GREY_800),
        ft.Container(content=signals_list, expand=True)
    )


# Mount Flet App safely onto /dashboard route with Absolute Path
assets_path = os.path.join(os.path.dirname(__file__), "assets")
app.mount("/dashboard", flet_fastapi.app(main_ui, assets_dir=assets_path))

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)