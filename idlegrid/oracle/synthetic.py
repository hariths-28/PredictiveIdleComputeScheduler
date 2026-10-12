import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_synthetic_logs(num_records=5000):
    """Generates synthetic telemetry data representing student laptop usage patterns."""
    np.random.seed(42)
    start_time = datetime.now() - timedelta(days=7)
    
    timestamps = [start_time + timedelta(minutes=5 * i) for i in range(num_records)]
    
    data = []
    for ts in timestamps:
        hour = ts.hour
        day = ts.weekday() # 0 = Monday, 6 = Sunday
        is_weekend = 1 if day >= 5 else 0
        
        # Simulate realistic student behavior patterns
        # 02:00 - 08:00 -> Sleeping (High chance of long idle)
        if 2 <= hour < 8:
            is_idle = np.random.choice([1, 0], p=[0.92, 0.08])
            idle_duration = np.random.normal(120, 30) if is_idle else np.random.normal(5, 2)
        # 10:00 - 16:00 -> Class / Studying (Intermittent idle)
        elif 10 <= hour < 16 and not is_weekend:
            is_idle = np.random.choice([1, 0], p=[0.50, 0.50])
            idle_duration = np.random.normal(45, 15) if is_idle else np.random.normal(3, 1)
        # 19:00 - 23:00 -> Active use / Gaming / Streaming (Low idle)
        elif 19 <= hour < 23:
            is_idle = np.random.choice([1, 0], p=[0.15, 0.85])
            idle_duration = np.random.normal(15, 5) if is_idle else np.random.normal(2, 1)
        else:
            is_idle = np.random.choice([1, 0], p=[0.40, 0.60])
            idle_duration = np.random.normal(30, 10) if is_idle else np.random.normal(4, 2)
            
        idle_duration = max(0.0, idle_duration)
        
        # CPU/RAM/Input features based on idle state
        if is_idle and idle_duration > 5:
            cpu_pct = np.random.uniform(2.0, 15.0)
            ram_pct = np.random.uniform(25.0, 50.0)
            mouse_events = 0
            key_events = 0
        else:
            cpu_pct = np.random.uniform(25.0, 90.0)
            ram_pct = np.random.uniform(50.0, 85.0)
            mouse_events = np.random.randint(5, 120)
            key_events = np.random.randint(2, 80)
            
        data.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "cpu_pct": round(cpu_pct, 2),
            "ram_pct": round(ram_pct, 2),
            "mouse_events_last_min": mouse_events,
            "key_events_last_min": key_events,
            "battery_charging": np.random.choice([0, 1], p=[0.3, 0.7]),
            "uninterrupted_idle_minutes": round(idle_duration, 1)  # TARGET VARIABLE
        })
        
    df = pd.DataFrame(data)
    df.to_csv("laptop_telemetry.csv", index=False)
    print(f"Dataset generated with {num_records} rows saved to 'laptop_telemetry.csv'")

if __name__ == "__main__":
    generate_synthetic_logs()