import logging
import os
import requests
from dotenv import load_dotenv
import flet as ft

# Load environment variables
load_dotenv()

API_URL = os.getenv("API_URL", "https://quotex-ai-backend-zzp8.onrender.com/api/v1/get-signal")
API_KEY = os.getenv("API_KEY", "")

# Version Compatibility Layer (Flet 0.23 vs 0.28+)
Colors = getattr(ft, "Colors", getattr(ft, "colors", None))
Icons = getattr(ft, "Icons", getattr(ft, "icons", None))

def main(page: ft.Page):
    page.title = "Quotex AI Signal System"
    page.theme_mode = ft.ThemeMode.DARK
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.padding = 20

    # Header Title
    title_text = ft.Text(
        "Quotex AI Signal",
        size=26,
        weight=ft.FontWeight.BOLD,
        color=Colors.CYAN_ACCENT
    )
    
    # Timeframe Dropdown
    timeframe_dropdown = ft.Dropdown(
        width=160,
        label="Timeframe",
        value="1m",
        options=[
            ft.dropdown.Option("1m"),
            ft.dropdown.Option("5m"),
            ft.dropdown.Option("10m"),
            ft.dropdown.Option("15m"),
            ft.dropdown.Option("30m"),
            ft.dropdown.Option("1hr"),
        ],
    )

    # UI Display Labels
    asset_text = ft.Text("Asset: --", size=18, weight=ft.FontWeight.BOLD)
    direction_text = ft.Text("Direction: --", size=22, weight=ft.FontWeight.BOLD)
    score_text = ft.Text("Score: --", size=16)
    percentage_text = ft.Text("Accuracy: --", size=16)
    status_text = ft.Text("Press 'Fetch Signal' to scan market", size=13, color=Colors.GREY_400)
    
    loading_ring = ft.ProgressRing(visible=False)

    # API Request Logic
    def fetch_signal(e):
        loading_ring.visible = True
        fetch_btn.disabled = True
        status_text.value = "Scanning market for best signals..."
        status_text.color = Colors.YELLOW_ACCENT
        page.update()

        try:
            if not API_KEY:
                status_text.value = "Error: API Key is missing in .env!"
                status_text.color = Colors.RED_ACCENT
                return

            headers = {"X-API-Key": API_KEY}
            params = {"timeframe": timeframe_dropdown.value}
            
            response = requests.get(API_URL, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "SUCCESS":
                    asset_text.value = f"Asset: {data.get('asset', 'N/A')}"
                    direction = data.get("direction", "--")
                    direction_text.value = f"Direction: {direction}"
                    
                    if direction in ["UP", "CALL", "BUY"]:
                        direction_text.color = Colors.GREEN_ACCENT_400
                    elif direction in ["DOWN", "PUT", "SELL"]:
                        direction_text.color = Colors.RED_ACCENT_400
                    else:
                        direction_text.color = Colors.WHITE

                    score_text.value = f"Score: {data.get('score', 'N/A')}"
                    percentage_text.value = f"Accuracy: {data.get('percentage', 'N/A')}"
                    status_text.value = "Signal Received Successfully!"
                    status_text.color = Colors.GREEN_400
                else:
                    msg = data.get("message", "No signal available right now")
                    status_text.value = f"Notice: {msg}"
                    status_text.color = Colors.ORANGE_ACCENT
            else:
                status_text.value = f"Error {response.status_code}: Unauthorized / Server Issue"
                status_text.color = Colors.RED_ACCENT

        except Exception as err:
            status_text.value = f"Connection Error: {str(err)}"
            status_text.color = Colors.RED_ACCENT

        finally:
            loading_ring.visible = False
            fetch_btn.disabled = False
            page.update()

    # Signal Card UI
    signal_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    asset_text,
                    direction_text,
                    score_text,
                    percentage_text,
                    ft.Divider(),
                    status_text,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=20,
            width=320,
        ),
        elevation=6,
    )

    # Button
    fetch_btn = ft.ElevatedButton(
        "FETCH SIGNAL",
        icon=Icons.BOLT_ROUNDED,
        on_click=fetch_signal,
        style=ft.ButtonStyle(
            color=Colors.BLACK,
            bgcolor=Colors.CYAN_ACCENT,
        ),
        width=200,
        height=45
    )

    # Layout Setup
    page.add(
        title_text,
        ft.Divider(),
        timeframe_dropdown,
        ft.Container(height=10),
        signal_card,
        ft.Container(height=10),
        loading_ring,
        fetch_btn
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Render-এর জন্য ডাইনামিক পোর্ট এবং ওয়েব সার্ভার কনফিগারেশন
    port = int(os.environ.get("PORT", 10000))
    ft.app(target=main, view=None, port=port, host="0.0.0.0")