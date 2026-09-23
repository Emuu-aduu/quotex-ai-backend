import json
import logging
import time
from typing import Dict, Any, Optional
import zmq

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class ZMQPublisher:
    """
    Phase 1 Point 8: High-Performance ZeroMQ Publisher Engine.
    Distributes WebSocket market ticks to internal processing layers with sub-millisecond latency.
    """
    def __init__(self, port: int = 5555):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(f"tcp://*:{self.port}")
        logging.info(f"ZeroMQ Publisher bound to port {self.port}")

    def publish_tick(self, topic: str, data: Dict[str, Any]) -> None:
        """Publishes a tick payload over the ZeroMQ bus."""
        try:
            payload = json.dumps(data)
            self.socket.send_string(f"{topic} {payload}")
        except Exception as e:
            logging.error(f"Error publishing ZMQ message: {e}")

    def close(self) -> None:
        """Gracefully terminates ZeroMQ sockets."""
        self.socket.close()
        self.context.term()
        logging.info("ZeroMQ Publisher terminated cleanly.")


class ZMQSubscriber:
    """ZeroMQ Subscriber Engine for consuming tick streams."""
    def __init__(self, port: int = 5555, topic: str = "TICK"):
        self.port = port
        self.topic = topic
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(f"tcp://localhost:{self.port}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, self.topic)
        # Set 1-second timeout for non-blocking execution during testing
        self.socket.setsockopt(zmq.RCVTIMEO, 1000)

    def receive_tick(self) -> Optional[Dict[str, Any]]:
        """Non-blocking tick retriever."""
        try:
            message = self.socket.recv_string()
            topic, payload = message.split(" ", 1)
            return json.loads(payload)
        except zmq.Again:
            return None  # Timeout hit
        except Exception as e:
            logging.error(f"Error receiving ZMQ message: {e}")
            return None

    def close(self) -> None:
        self.socket.close()
        self.context.term()


# --- Self-Testing Simulation Mode ---
if __name__ == "__main__":
    print("--- Testing Phase 1 Point 8: ZeroMQ Messaging Pipeline ---")
    
    pub = ZMQPublisher(port=5555)
    sub = ZMQSubscriber(port=5555, topic="TICK")

    # Give ZeroMQ socket slow-joiner time to connect
    time.sleep(0.2)

    # Mock Tick Payload
    mock_payload = {
        "symbol": "EURUSD",
        "price": 1.08542,
        "timestamp": time.time(),
        "source": "QUOTEX"
    }

    print("\n1. Publishing Mock Tick via ZeroMQ Bus...")
    pub.publish_tick("TICK", mock_payload)

    print("2. Receiving Published Tick from ZeroMQ Bus...")
    received_data = sub.receive_tick()

    if received_data and received_data.get("symbol") == "EURUSD":
        print(f">> [ZMQ SUCCESS] Received Tick: {received_data}")
        print("\n>> PHASE 1 ENTIRE PIPELINE COMPLETED SUCCESSFULLY! <<")
    else:
        print(">> [ZMQ ERROR] Failed to receive published tick! <<")

    pub.close()
    sub.close()