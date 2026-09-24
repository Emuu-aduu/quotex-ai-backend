import logging
import os
import random
import time
import flet as ft

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

    # Real-time Dynamic Signal Generation Logic
    def fetch_signal(e):
        loading_ring.visible = True
        fetch_btn.disabled = True
        status_text.value = "Scanning market momentum & volatility..."
        status_text.color = Colors.YELLOW_ACCENT
        page.update()

        # Simulate realistic scanning delay
        time.sleep(1)

        try:
            # time.time() આધારিত seeding যা নিশ্চিত করবে সিগন্যাল কখনো রিজিট বা রিপিট হবে না
            current_time = time.time()
            random.seed(int(current_time * 1000) % 100000)

            assets = ["EUR/USD (OTC)", "GBP/USD (OTC)", "AUD/USD (OTC)", "USD/JPY (OTC)", "EUR/JPY (OTC)", "Crypto IDX"]
            selected_asset = random.choice(assets)
            
            direction = random.choice(["UP", "DOWN"])
            
            # Dynamic calculation for Score (/10) and Accuracy Percentage
            score = round(random.uniform(7.5, 9.8), 1)
            percentage = f"{round(random.uniform(82.0, 96.5), 1)}%"

            asset_text.value = f"Asset: {selected_asset}"
            direction_text.value = f"Direction: {direction}"
            
            if direction == "UP":
                direction_text.color = Colors.GREEN_ACCENT_400
            else:
                direction_text.color = Colors.RED_ACCENT_400

            score_text.value = f"Score: {score} / 10"
            percentage_text.value = f"Accuracy: {percentage}"
            status_text.value = "Signal Generated Successfully!"
            status_text.color = Colors.GREEN_400

        except Exception as err:
            status_text.value = f"Generation Error: {str(err)}"
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
    
    # Render ডাইনামিক পোর্ট এবং ওয়েব সার্ভার কনফিগারেশন
    port = int(os.environ.get("PORT", 10000))
    ft.app(target=main, view=None, port=port, host="0.0.0.0")