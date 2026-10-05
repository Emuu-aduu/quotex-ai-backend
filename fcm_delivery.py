import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("FCMDelivery")

# ---------------------------------------------------------
# Defensive Firebase Admin SDK Import
# ---------------------------------------------------------
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logger.warning("firebase-admin package not installed. FCM Push notifications will be disabled.")


class FCMDeliveryService:
    """
    Handles Browser & Mobile Push Notifications via Firebase Cloud Messaging (FCM).
    Safely degrades if Firebase credentials or SDK are missing.
    """

    def __init__(self, cred_path: Optional[str] = None):
        self.initialized = False
        if not FIREBASE_AVAILABLE:
            return

        # Load Firebase Service Account Credentials Path
        cred_file = cred_path or os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_service_account.json")

        if os.path.exists(cred_file):
            try:
                if not firebase_admin._apps:
                    cred = credentials.Certificate(cred_file)
                    firebase_admin.initialize_app(cred)
                self.initialized = True
                logger.info("[FCM] Firebase Cloud Messaging initialized successfully.")
            except Exception as err:
                logger.error(f"[FCM] Failed to initialize Firebase Admin SDK: {err}")
        else:
            logger.info(f"[FCM] Credentials file '{cred_file}' not found. Push delivery running in dummy mode.")

    def send_signal_notification(
        self,
        title: str,
        body: str,
        topic: str = "trading_signals",
        data: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Sends push notification broadcast to a specific topic channel (e.g., 'trading_signals').
        """
        if not self.initialized:
            logger.debug("[FCM] Service not active. Skipping push delivery.")
            return False

        try:
            # Ensure data payload values are strings (FCM Requirement)
            safe_data = {str(k): str(v) for k, v in (data or {}).items()}

            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=safe_data,
                topic=topic
            )
            response = messaging.send(message)
            logger.info(f"[FCM] Push Notification sent successfully. Msg ID: {response}")
            return True
        except Exception as err:
            logger.error(f"[FCM] Error sending push notification: {err}")
            return False


if __name__ == "__main__":
    # Isolated module test
    logging.basicConfig(level=logging.INFO)
    fcm_service = FCMDeliveryService()
    test_res = fcm_service.send_signal_notification(
        title="EURUSD Buy Signal",
        body="Price: 1.0850 | Confidence: 85%",
        data={"symbol": "EURUSD", "action": "BUY"}
    )
    print(f"FCM Test Result: {test_res}")