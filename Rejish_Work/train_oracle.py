import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

def preprocess_and_train(csv_path="laptop_telemetry.csv"):
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Feature Engineering
    # 1. Temporal features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].apply(lambda x: 1 if x >= 5 else 0)
    
    # 2. Cyclical transformation for hours (23 to 0 transition optimization)
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24.0)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24.0)
    
    # Define Feature matrix (X) and Target (y)
    feature_cols = [
        'hour_sin', 'hour_cos', 'day_of_week', 'is_weekend',
        'cpu_pct', 'ram_pct', 'mouse_events_last_min', 
        'key_events_last_min', 'battery_charging'
    ]
    
    X = df[feature_cols]
    y = df['uninterrupted_idle_minutes']
    
    # Train / Test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Initialize Random Forest Regressor
    rf_model = RandomForestRegressor(
        n_estimators=100,
        max_depth=12,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1
    )
    
    print("Training Random Forest Oracle model...")
    rf_model.fit(X_train, y_train)
    
    # Evaluate
    predictions = rf_model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)
    
    print(f"\n--- Model Evaluation ---")
    print(f"Mean Absolute Error (MAE): {mae:.2f} minutes")
    print(f"R² Score: {r2:.3f}")
    
    # Feature Importance Analysis
    importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': rf_model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print("\n--- Feature Importances ---")
    print(importance.to_string(index=False))
    
    # Save Model Artifact
    model_payload = {
        "model": rf_model,
        "feature_cols": feature_cols
    }
    joblib.dump(model_payload, "oracle_rf_model.joblib")
    print("\nSaved model artifact to 'oracle_rf_model.joblib'")

if __name__ == "__main__":
    preprocess_and_train()