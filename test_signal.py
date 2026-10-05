# -*- coding: utf-8 -*-
import requests
from config import settings

# Target endpoint (Local or Ngrok) without URL query parameters
URL = "http://127.0.0.1:8000/webhook"

# Secure authentication via Headers using the configuration manager
HEADERS = {
    "Content-Type": "application/json",
    "X-Webhook-Secret": settings.WEBHOOK_SECRET
}

# Real market asset payload matching approved core pairs
PAYLOAD = {
    "symbol": "EURUSD",
    "action": "BUY",
    "timeframe": "15m",
    "price": 1.0850
}

def send_test_signal():
    try:
        response = requests.post(URL, json=PAYLOAD, headers=HEADERS, timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except requests.exceptions.Timeout:
        print("Error: Request timed out!")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the server. Make sure main.py is running.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    send_test_signal()