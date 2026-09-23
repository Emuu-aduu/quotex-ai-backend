import time
import json
import threading
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

def test_1_config():
    logging.info("1. Testing Config & Whitelist System...")
    from config import settings
    assert hasattr(settings, "BINANCE_BASE_WS_URL"), "BINANCE_BASE_WS_URL missing!"
    assert settings.is_approved_live_pair("EUR/USD") == True, "EUR/USD should be approved!"
    assert settings.is_approved_live_pair("EURUSD_OTC") == False, "OTC pair must be rejected!"
    logging.info("[PASS] Config & Whitelist guards functional.")

def test_2_zmq_bus():
    logging.info("2. Testing ZeroMQ Messaging Bus...")
    from zmq_bus import ZMQPublisher, ZMQSubscriber
    pub = ZMQPublisher(port=5556)
    sub = ZMQSubscriber(port=5556, topic="TICK")
    time.sleep(0.2)
    
    test_msg = {"symbol": "EURUSD", "price": 1.0850, "timestamp": time.time()}
    pub.publish_tick("TICK", test_msg)
    recv_msg = sub.receive_tick()
    
    pub.close()
    sub.close()
    assert recv_msg is not None and recv_msg["symbol"] == "EURUSD", "ZMQ message delivery failed!"
    logging.info("[PASS] ZeroMQ Pub/Sub pipeline verified.")

def test_3_quotex_guards():
    logging.info("3. Testing Quotex Protection Guards...")
    from quotex_feed import QuotexDataFeed
    feed = QuotexDataFeed()
    
    class MockWS:
        def __init__(self): self.closed = False
        def close(self): self.closed = True
            
    mock_ws = MockWS()
    assert feed._validate_and_process_payload(mock_ws, "EURUSD_OTC", 1.0850, time.time()) == False
    logging.info("[PASS] Quotex Disconnect guards verified.")

def test_4_binance_live():
    logging.info("4. Testing Binance Backup Stream...")
    from binance_backup import BinanceBackupFeed
    feed = BinanceBackupFeed()
    received_ticks = []
    
    orig_on_message = feed._on_message
    def custom_on_message(ws, message):
        orig_on_message(ws, message)
        try:
            data = json.loads(message)
            if float(data.get("p", 0.0)) > 0: received_ticks.append(data)
        except Exception: pass
            
    feed._on_message = custom_on_message
    t = threading.Thread(target=feed.start, daemon=True)
    t.start()
    time.sleep(2)
    feed.is_running = False
    if feed.ws: feed.ws.close()
        
    assert len(received_ticks) > 0, "No live ticks from Binance!"
    logging.info(f"[PASS] Binance Stream verified ({len(received_ticks)} ticks received).")

def test_5_hybrid_cache():
    logging.info("5. Testing Hybrid Cache Manager...")
    from cache_manager import HybridCacheManager
    cache = HybridCacheManager()
    
    test_data = {"symbol": "EURUSD", "action": "BUY", "price": 1.0854, "active": True}
    cache.set("test_key", test_data, ttl_seconds=10)
    res = cache.get("test_key")
    
    assert res is not None and res["active"] == True, "Cache retrieval failed!"
    logging.info("[PASS] Hybrid Cache Engine verified.")

def test_6_fcm_broadcaster():
    logging.info("6. Testing FCM Notification Broadcaster...")
    from fcm_delivery import FCMPushBroadcaster
    fcm = FCMPushBroadcaster()
    
    signal = {"symbol": "EURUSD", "action": "SELL", "price": 1.0840, "timestamp": "NOW"}
    status = fcm.send_signal_notification(signal)
    
    assert status == True, "FCM Push notification test failed!"
    logging.info("[PASS] FCM Notification Engine verified.")

def test_7_duckdb_storage():
    logging.info("7. Testing DuckDB Core Storage Engine...")
    from db_store import DuckDBStorageEngine
    db = DuckDBStorageEngine("master_test.duckdb")
    
    mock_tick = {"symbol": "GBPUSD", "price": 1.2650, "timestamp": time.time(), "source": "TEST"}
    db.insert_tick(mock_tick)
    ticks = db.get_recent_ticks("GBPUSD", limit=1)
    db.close()
    
    assert len(ticks) > 0 and ticks[0]["symbol"] == "GBPUSD", "DuckDB store/query failed!"
    logging.info("[PASS] DuckDB Core Storage Engine verified.")

def test_8_mlops_db():
    logging.info("8. Testing DuckDB MLOps Feature Store...")
    from mlops_db import DuckDBMLOpsEngine
    db = DuckDBMLOpsEngine("master_mlops_test.duckdb")
    
    mock_feature = {
        "symbol": "EURUSD", "timestamp": time.time(),
        "open": 1.0850, "high": 1.0860, "low": 1.0845, "close": 1.0855,
        "rsi_14": 58.4, "ema_9": 1.0852, "ema_21": 1.0848
    }
    db.log_features(mock_feature)
    records = db.get_latest_features("EURUSD", limit=1)
    db.close()
    
    assert len(records) > 0 and records[0]["symbol"] == "EURUSD", "MLOps Feature Store test failed!"
    logging.info("[PASS] DuckDB MLOps Feature Store verified.")

def test_9_mlflow_pipeline():
    logging.info("9. Testing Standalone MLOps Workflow Pipeline...")
    from mlops_db import DuckDBMLOpsEngine
    from mlflow_tracker import StandaloneMLflowTracker, StandaloneWorkflowExecutor
    
    db = DuckDBMLOpsEngine("master_mlops_test.duckdb")
    tracker = StandaloneMLflowTracker("./master_mlruns")
    executor = StandaloneWorkflowExecutor(db, tracker)
    
    success = executor.execute_pipeline("EURUSD")
    db.close()
    
    assert success == True, "Standalone MLOps Workflow pipeline failed!"
    logging.info("[PASS] Standalone MLOps Workflow Pipeline verified.")

def run_all_tests():
    print("\n==================================================")
    print("    MASTER INTEGRATION TEST SUITE (PHASES 1 - 3)  ")
    print("==================================================")
    
    tests = [
        ("Config Whitelist", test_1_config),
        ("ZeroMQ Bus Engine", test_2_zmq_bus),
        ("Quotex Guards", test_3_quotex_guards),
        ("Binance Live Feed", test_4_binance_live),
        ("Hybrid Cache", test_5_hybrid_cache),
        ("FCM Broadcaster", test_6_fcm_broadcaster),
        ("DuckDB Core Storage", test_7_duckdb_storage),
        ("DuckDB MLOps Feature Store", test_8_mlops_db),
        ("Standalone MLOps Pipeline", test_9_mlflow_pipeline)
    ]
    
    passed_count = 0
    for name, test_func in tests:
        try:
            test_func()
            passed_count += 1
        except Exception as e:
            logging.error(f"[FAIL] {name} test failed: {e}")
            
    print("\n==================================================")
    print(f"       SUMMARY: {passed_count}/{len(tests)} TESTS PASSED")
    if passed_count == len(tests):
        print("   STATUS: SYSTEM IS 100% HEALTHY & READY!")
    else:
        print("   STATUS: ISSUES DETECTED - PLEASE REVIEW LOGS")
    print("==================================================\n")

if __name__ == "__main__":
    run_all_tests()