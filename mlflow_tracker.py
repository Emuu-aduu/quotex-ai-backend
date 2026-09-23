import os
import json
import time
import logging
from typing import Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

class StandaloneMLflowTracker:
    """
    Phase 3 Points 3 & 4: Standalone MLflow Tracker.
    Uses local file directory backend (./mlruns) without needing external MLflow servers or databases.
    Lazy experiment creation on log call.
    """
    def __init__(self, tracking_dir: str = "./mlruns"):
        self.tracking_dir = tracking_dir
        os.makedirs(self.tracking_dir, exist_ok=True)
        self.use_mlflow = False
        self._init_mlflow()

    def _init_mlflow(self) -> None:
        try:
            import mlflow
            mlflow.set_tracking_uri(f"file://{os.path.abspath(self.tracking_dir)}")
            self.use_mlflow = True
            logging.info(f"[MLFLOW] Local backend tracking URI set to '{self.tracking_dir}'.")
        except ImportError:
            logging.warning("[MLFLOW] mlflow package not installed. Running in Standalone Directory Mode.")
            self.use_mlflow = False

    def log_experiment(self, run_name: str, params: Dict[str, Any], metrics: Dict[str, Any], experiment_name: str = "AEmuu_Trading_MLOps") -> str:
        run_id = f"run_{int(time.time())}"
        if self.use_mlflow:
            import mlflow
            # Set experiment on execution time to avoid premature creation during import
            mlflow.set_experiment(experiment_name)
            with mlflow.start_run(run_name=run_name) as run:
                mlflow.log_params(params)
                mlflow.log_metrics(metrics)
                run_id = run.info.run_id
                logging.info(f"[MLFLOW] Logged run '{run_name}' under experiment '{experiment_name}' (Run ID: {run_id})")
        else:
            # Fallback Local JSON Directory Tracker
            run_data = {
                "run_id": run_id,
                "run_name": run_name,
                "experiment_name": experiment_name,
                "timestamp": time.time(),
                "params": params,
                "metrics": metrics
            }
            filepath = os.path.join(self.tracking_dir, f"{run_id}.json")
            with open(filepath, "w") as f:
                json.dump(run_data, f, indent=2)
            logging.info(f"[STANDALONE MLOPS] Logged experiment run locally: {filepath}")
        return run_id


class StandaloneWorkflowExecutor:
    """
    Standalone Orchestrator replacing heavy Airflow overhead for 5-10 users.
    Executes Feature extraction, ML evaluation, and local tracking sequentially.
    """
    def __init__(self, db_engine, tracker):
        self.db = db_engine
        self.tracker = tracker

    def execute_pipeline(self, symbol: str) -> bool:
        logging.info(f"[WORKFLOW] Executing Standalone Pipeline for '{symbol}'...")
        
        # Step 1: Feature Extraction
        features = self.db.get_latest_features(symbol, limit=10)
        logging.info(f"[WORKFLOW Step 1/3] Extracted {len(features)} records from DuckDB Feature Store.")
        
        # Step 2: Model Evaluation Simulation
        params = {"model": "RandomForest_Classifier", "n_estimators": 100, "max_depth": 6}
        metrics = {"accuracy": 0.885, "win_rate": 0.72}
        
        # Step 3: Log to MLflow Local Backend
        run_id = self.tracker.log_experiment(f"Train_{symbol}", params, metrics)
        logging.info(f"[WORKFLOW Step 3/3] Standalone Pipeline execution completed successfully!")
        return True


if __name__ == "__main__":
    from mlops_db import DuckDBMLOpsEngine
    
    db = DuckDBMLOpsEngine()
    tracker = StandaloneMLflowTracker()
    executor = StandaloneWorkflowExecutor(db, tracker)
    
    executor.execute_pipeline("EURUSD")
    db.close()