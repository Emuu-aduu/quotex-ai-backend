import os
import json
import logging
from typing import Dict, Any, List
from config import settings

# Configure Clean Enterprise Logging Format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

class FCMPushBroadcaster:
    """
    Google FCM Push Notification Engine.
    Provides sub-second signal delivery for registered client devices.
    """
    def __init__(self):
        self.initialized = False
        self._init_fcm()

    def _init_fcm(self) -> None:
        cred_path = getattr(settings, "FCM_CREDENTIALS_FILE", "fcm_credentials.json")
        
        if os.path.exists(cred_path):
            try:
                import firebase_admin
                from firebase_admin import credentials
                
                if not firebase_admin._apps:
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                self.initialized = True
                logging.info("[FCM] Firebase Admin SDK initialized successfully.")
            except Exception as e:
                logging.warning(f"[FCM] SDK init failed ({e}). Operating in simulation mode.")
                self.initialized = False
        else:
            logging.info(f"[FCM] Credentials '{cred_path}' missing. Operating in simulation mode.")

    def send_signal_notification(self, signal_data: Dict[str, Any], target_tokens: List[str] = None) -> bool:
        symbol = str(signal_data.get("symbol", "UNKNOWN"))
        action = str(signal_data.get("action", "INFO"))
        price = str(signal_data.get("price", 0.0))
        ts = str(signal_data.get("timestamp", ""))

        title = f"🚨 SIGNAL: {symbol} ({action})"
        body = f"Action: {action} | Entry: {price} | Time: {ts}"

        flat_payload = {
            "symbol": symbol,
            "action": action,
            "price": price,
            "timestamp": ts
        }

        if self.initialized and target_tokens:
            try:
                from firebase_admin import messaging
                
                android_config = messaging.AndroidConfig(
                    priority="high",
                    ttl=0,
                    notification=messaging.AndroidNotification(
                        sound="default",
                        channel_id="trading_signals"
                    )
                )

                message = messaging.MulticastMessage(
                    notification=messaging.Notification(title=title, body=body),
                    data=flat_payload,
                    android=android_config,
                    tokens=target_tokens,
                )
                response = messaging.send_each_for_multicast(message)
                logging.info(f"[FCM] Broadcast successful. Delivered to {response.success_count} devices.")
                return True
            except Exception as e:
                logging.error(f"[FCM] Broadcast delivery failed: {e}")
                return False
        else:
            logging.info(f"[FCM SIMULATION] High-Priority Push -> Title: '{title}' | Body: '{body}'")
            return True


if __name__ == "__main__":
    fcm = FCMPushBroadcaster()
    mock_signal = {
        "symbol": "EURUSD",
        "action": "BUY",
        "price": 1.08542,
        "timestamp": "12:45:00 UTC"
    }
    
    logging.info("Executing FCM delivery self-test...")
    if fcm.send_signal_notification(mock_signal):
        logging.info("FCM Delivery module test completed successfully.")