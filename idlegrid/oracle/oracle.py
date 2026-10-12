import joblib
import numpy as np
import pandas as pd
from datetime import datetime

class MLOracle:
    def __init__(self, model_path="oracle_rf_model.joblib"):
        try:
            payload = joblib.load(model_path)
            self.model = payload["model"]
            self.feature_cols = payload["feature_cols"]
            self.ready = True
        except Exception as e:
            print(f"Warning: ML Oracle model failed to load ({e}). Falling back to Naive Rules.")
            self.ready = False

    def predict_idle_minutes(self, node_stats: dict) -> float:
        """
        Calculates predicted uninterrupted idle minutes for a given laptop status dict.
        
        Expected node_stats keys:
        - cpu_pct (float)
        - ram_pct (float)
        - mouse_events_last_min (int)
        - key_events_last_min (int)
        - battery_charging (int 0/1)
        """
        if not self.ready:
            # Naive Fallback: If CPU < 15 and no mouse movement, assume 15 mins
            if node_stats.get('cpu_pct', 100) < 15.0 and node_stats.get('mouse_events_last_min', 1) == 0:
                return 15.0
            return 0.0

        now = datetime.now()
        hour = now.hour
        day_of_week = now.weekday()
        
        input_data = {
            'hour_sin': np.sin(2 * np.pi * hour / 24.0),
            'hour_cos': np.cos(2 * np.pi * hour / 24.0),
            'day_of_week': day_of_week,
            'is_weekend': 1 if day_of_week >= 5 else 0,
            'cpu_pct': float(node_stats.get('cpu_pct', 50.0)),
            'ram_pct': float(node_stats.get('ram_pct', 50.0)),
            'mouse_events_last_min': int(node_stats.get('mouse_events_last_min', 0)),
            'key_events_last_min': int(node_stats.get('key_events_last_min', 0)),
            'battery_charging': int(node_stats.get('battery_charging', 1))
        }

        features_df = pd.DataFrame([input_data])[self.feature_cols]
        predicted_minutes = self.model.predict(features_df)[0]
        return max(0.0, round(float(predicted_minutes), 1))

    def evaluate_node_suitability(self, node_stats: dict, required_job_minutes: float, safety_buffer: float = 2.0) -> dict:
        """
        Main decision function for Role 2 (Dispatcher).
        Returns whether to schedule on this node and the confidence reason.
        """
        predicted_idle = self.predict_idle_minutes(node_stats)
        target_needed = required_job_minutes + safety_buffer
        
        is_suitable = predicted_idle >= target_needed
        
        return {
            "is_suitable": is_suitable,
            "predicted_idle_minutes": predicted_idle,
            "required_minutes": required_job_minutes,
            "reason": "Sufficient predicted idle capacity" if is_suitable else f"Predicted idle ({predicted_idle}m) below requirement ({target_needed}m)"
        }

# Example Usage Test
if __name__ == "__main__":
    oracle = MLOracle()
    
    # Test Laptop Status (Idle during nighttime)
    sample_laptop_idle = {
        "cpu_pct": 5.2,
        "ram_pct": 32.0,
        "mouse_events_last_min": 0,
        "key_events_last_min": 0,
        "battery_charging": 1
    }
    
    # Test decision for a 10-minute ML job
    decision = oracle.evaluate_node_suitability(sample_laptop_idle, required_job_minutes=10.0)
    print("Decision Result:", decision)