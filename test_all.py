import os
import sys
import unittest
import logging

# Suppress noisy logs during unittest execution
logging.basicConfig(level=logging.ERROR)

# ---------------------------------------------------------
# Defensive Module Imports with Clear Diagnostics
# ---------------------------------------------------------
try:
    from config import settings
    from db_store import DuckDBStorageEngine
    from cache_manager import HybridCacheManager
except ImportError as err:
    print(f"\n[CRITICAL ERROR] Missing required project module: {err}")
    print("Ensure 'config.py', 'db_store.py', and 'cache_manager.py' are present in the working directory before running tests.\n")
    sys.exit(1)


class TestSignalEngineCore(unittest.TestCase):
    """Automated Unit & Integration Test Suite for TradingView Signal Engine."""

    def setUp(self):
        """Test setup for isolated database and cache instances."""
        self.test_db_path = "test_run_temp.duckdb"
        self.db = DuckDBStorageEngine(self.test_db_path)
        self.cache = HybridCacheManager()

    def tearDown(self):
        """Robust cleanup using try/finally block to guarantee temporary file removal."""
        try:
            if hasattr(self, 'db') and self.db:
                self.db.close()
        except Exception as close_err:
            logging.error(f"Error while closing DuckDB test instance: {close_err}")
        finally:
            if os.path.exists(self.test_db_path):
                try:
                    os.remove(self.test_db_path)
                except Exception as remove_err:
                    logging.warning(f"Could not remove temporary test DB file: {remove_err}")

    # 1. Config Loading Test
    def test_01_config_loading(self):
        self.assertIsNotNone(settings.WEBHOOK_SECRET)
        self.assertGreater(settings.PORT, 0)
        self.assertIn(settings.ENV, ["development", "production", "testing"])

    # 2. DuckDB Engine Operations Test
    def test_02_duckdb_storage_operations(self):
        sample_signal = {
            "signal_id": "TEST_SIG_001",
            "symbol": "EURUSD",
            "action": "BUY",
            "timeframe": "1m",
            "price": 1.0850,
            "timestamp": "2026-10-02T10:00:00Z"
        }
        
        # Save Signal
        save_success = self.db.save_signal(sample_signal)
        self.assertTrue(save_success)

        # Retrieve Signal History
        history = self.db.get_recent_signals(limit=5)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["symbol"], "EURUSD")

    # 3. Hybrid Cache Manager Test
    def test_03_cache_set_get(self):
        key = "test_indicator_ma"
        val = {"sma_20": 1.0845, "status": "bullish"}
        
        # Set Cache
        self.cache.set(key, val, ttl_seconds=10)
        
        # Get Cache
        retrieved = self.cache.get(key)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.get("status"), "bullish")

    # 4. Signal Deduplication Check
    def test_04_signal_deduplication(self):
        sig_hash = "hash_eurusd_buy_1m_1000"
        
        # First check (Should be False / Not duplicate)
        is_dup_1 = self.cache.is_duplicate_signal(sig_hash)
        self.assertFalse(is_dup_1)

        # Mark as processed
        self.cache.mark_signal_processed(sig_hash, ttl_seconds=60)

        # Second check (Should be True / Duplicate)
        is_dup_2 = self.cache.is_duplicate_signal(sig_hash)
        self.assertTrue(is_dup_2)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("       RUNNING TRADINGVIEW SIGNAL BOT TEST SUITE")
    print("=" * 60)
    unittest.main(verbosity=2)