import os
import sys
import json
import pickle
import argparse
import logging
import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

MODEL_PATH = "data/ideal_twin/brix_model.pkl"
FEATURES_PATH = "data/merged/farm_features.csv"

def augment_data():
    """Generate synthetic farm records matching agricultural physical models for robust training."""
    np.random.seed(42)
    augmented_rows = []
    
    # 150 synthetic records
    for i in range(150):
        variety = np.random.choice(['CO_265', 'CO_86032', '8005'])
        crop_type = np.random.choice(['newly_planted', 'ratoon'])
        irrigation = np.random.choice(['drip', 'sprinkler', 'surface'])
        
        area = np.random.uniform(1.0, 10.0)
        n_val = np.random.uniform(50.0, 150.0)
        p_val = np.random.uniform(30.0, 100.0)
        k_val = np.random.uniform(30.0, 120.0)
        
        veg_interval = np.random.uniform(7.0, 20.0)
        rep_interval = np.random.uniform(7.0, 20.0)
        
        mean_ndvi = np.random.uniform(0.35, 0.75)
        max_ndvi = mean_ndvi + np.random.uniform(0.05, 0.20)
        mean_ndre = mean_ndvi * np.random.uniform(0.7, 0.9)
        mean_ndwi = np.random.uniform(-0.15, 0.2)
        mean_lst = np.random.uniform(22.0, 38.0)
        mean_temp = np.random.uniform(20.0, 32.0)
        total_precip = np.random.uniform(200.0, 1500.0)
        mean_rh = np.random.uniform(40.0, 85.0)
        mean_wind = np.random.uniform(1.0, 4.5)
        
        # Predicted brix base
        base_brix = 15.0
        
        # NDVI & NDRE positive correlation (biomass & chlorophyll concentration)
        base_brix += (mean_ndvi - 0.5) * 8.0
        base_brix += (mean_ndre - 0.4) * 6.0
        
        # Water/heat stress effects
        if mean_lst > 32.0:
            base_brix -= (mean_lst - 32.0) * 0.5
        if mean_ndwi < -0.05:  # Too dry
            base_brix -= abs(mean_ndwi + 0.05) * 4.0
        elif mean_ndwi > 0.15:  # Overwatered/waterlogged
            base_brix -= (mean_ndwi - 0.15) * 6.0
            
        # Nutrients (optimal nitrogen, high potassium boosts sugar transport)
        base_brix += (n_val - 100.0) * 0.01
        base_brix += (k_val - 60.0) * 0.02
        
        # Variety sugar potential properties
        if variety == 'CO_265':
            base_brix += 1.2
        elif variety == 'CO_86032':
            base_brix += 0.5
            
        brix = base_brix + np.random.normal(0, 0.5)
        brix = np.clip(brix, 8.0, 24.0)
        
        augmented_rows.append({
            'mean_NDVI': mean_ndvi,
            'max_NDVI': max_ndvi,
            'mean_NDRE': mean_ndre,
            'mean_NDWI': mean_ndwi,
            'mean_LST': mean_lst,
            'mean_temp': mean_temp,
            'total_precip': total_precip,
            'mean_RH': mean_rh,
            'mean_wind': mean_wind,
            'area_acres': area,
            'n_kg_per_acre': n_val,
            'p_kg_per_acre': p_val,
            'k_kg_per_acre': k_val,
            'irrigation_interval_veg': veg_interval,
            'irrigation_interval_rep': rep_interval,
            'variety': variety,
            'crop_type_clean': crop_type,
            'irrigation_type': irrigation,
            'brix': brix
        })
        
    return pd.DataFrame(augmented_rows)

def train_model():
    logging.info("Initiating model training for Brix sugar content predictor...")
    
    # 1. Load real data if available and aggregate it
    real_records = []
    if os.path.exists(FEATURES_PATH):
        try:
            df_real = pd.read_csv(FEATURES_PATH)
            if 'brix' in df_real.columns and not df_real['brix'].dropna().empty:
                for farm_id, group in df_real.groupby('farm_id'):
                    brix_val = group['brix'].dropna().first_valid_index()
                    if brix_val is None:
                        continue
                    real_brix = df_real.loc[brix_val, 'brix']
                    
                    # Extract averages
                    real_records.append({
                        'mean_NDVI': group['NDVI'].mean() if 'NDVI' in group.columns else 0.5,
                        'max_NDVI': group['NDVI'].max() if 'NDVI' in group.columns else 0.6,
                        'mean_NDRE': group['NDRE'].mean() if 'NDRE' in group.columns else 0.4,
                        'mean_NDWI': group['NDWI'].mean() if 'NDWI' in group.columns else 0.0,
                        'mean_LST': group['LST'].mean() if 'LST' in group.columns else 28.0,
                        'mean_temp': group['temperature_2m'].mean() if 'temperature_2m' in group.columns else 25.0,
                        'total_precip': group['total_precipitation_sum'].sum() if 'total_precipitation_sum' in group.columns else 500.0,
                        'mean_RH': group['relative_humidity'].mean() if 'relative_humidity' in group.columns else 60.0,
                        'mean_wind': group['wind_speed_10m'].mean() if 'wind_speed_10m' in group.columns else 2.0,
                        'area_acres': group['area_acres'].iloc[0] if 'area_acres' in group.columns else 3.0,
                        'n_kg_per_acre': group['n_kg_per_acre'].iloc[0] if 'n_kg_per_acre' in group.columns else 80.0,
                        'p_kg_per_acre': group['p_kg_per_acre'].iloc[0] if 'p_kg_per_acre' in group.columns else 40.0,
                        'k_kg_per_acre': group['k_kg_per_acre'].iloc[0] if 'k_kg_per_acre' in group.columns else 50.0,
                        'irrigation_interval_veg': group['irrigation_interval_veg'].iloc[0] if 'irrigation_interval_veg' in group.columns else 15.0,
                        'irrigation_interval_rep': group['irrigation_interval_rep'].iloc[0] if 'irrigation_interval_rep' in group.columns else 15.0,
                        'variety': group['variety'].iloc[0] if 'variety' in group.columns else 'CO_265',
                        'crop_type_clean': group['crop_type_clean'].iloc[0] if 'crop_type_clean' in group.columns else 'newly_planted',
                        'irrigation_type': group['irrigation_type'].iloc[0] if 'irrigation_type' in group.columns else 'unknown',
                        'brix': real_brix
                    })
        except Exception as e:
            logging.error(f"Error reading real farm features: {e}")
            
    df_real_agg = pd.DataFrame(real_records)
    df_synth = augment_data()
    
    # Concatenate real and synthetic data
    if not df_real_agg.empty:
        df_train = pd.concat([df_real_agg, df_synth], ignore_index=True)
        logging.info(f"Loaded {len(df_real_agg)} real records and combined with {len(df_synth)} synthetic records.")
    else:
        df_train = df_synth
        logging.info(f"Training entirely on {len(df_synth)} synthetic records (physical agricultural models).")
        
    # 2. Define Features & Pipeline
    categorical_features = ['variety', 'crop_type_clean', 'irrigation_type']
    numerical_features = [
        'mean_NDVI', 'max_NDVI', 'mean_NDRE', 'mean_NDWI', 'mean_LST',
        'mean_temp', 'total_precip', 'mean_RH', 'mean_wind', 'area_acres',
        'n_kg_per_acre', 'p_kg_per_acre', 'k_kg_per_acre',
        'irrigation_interval_veg', 'irrigation_interval_rep'
    ]
    
    X = df_train[numerical_features + categorical_features]
    y = df_train['brix']
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', 'passthrough', numerical_features),
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
        ])
        
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', RandomForestRegressor(n_estimators=100, random_state=42))
    ])
    
    # 3. Fit and Save
    pipeline.fit(X, y)
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(pipeline, f)
        
    logging.info(f"Brix sugar predictor model successfully trained and saved to {MODEL_PATH}")
    return pipeline

def predict_brix(farm_id, target_plan_json=None):
    # Load model
    if not os.path.exists(MODEL_PATH):
        pipeline = train_model()
    else:
        with open(MODEL_PATH, 'rb') as f:
            pipeline = pickle.load(f)
            
    # Look up live data JSON
    safe_name = str(farm_id).lower().replace(" ", "_")
    live_json = f"data/live_farms/{safe_name}_live.json"
    
    if not os.path.exists(live_json):
        print(f"Error: Live JSON file {live_json} not found. Cannot make a prediction.")
        sys.exit(1)
        
    with open(live_json, 'r') as f:
        live_data = json.load(f)
        
    # Get timeseries aggregates
    mean_ndvi = 0.5
    max_ndvi = 0.6
    mean_ndre = 0.4
    mean_ndwi = 0.0
    mean_lst = 28.0
    mean_temp = 25.0
    total_precip = 500.0
    mean_rh = 60.0
    mean_wind = 2.0
    
    def extract_values(lst):
        return [item['observed'] for item in lst if item.get('observed') is not None]
        
    ndvi_list = extract_values(live_data.get('NDVI', []))
    if ndvi_list:
        mean_ndvi = sum(ndvi_list) / len(ndvi_list)
        max_ndvi = max(ndvi_list)
        
    ndre_list = extract_values(live_data.get('NDRE', []))
    if ndre_list:
        mean_ndre = sum(ndre_list) / len(ndre_list)
        
    ndwi_list = extract_values(live_data.get('NDWI', []))
    if ndwi_list:
        mean_ndwi = sum(ndwi_list) / len(ndwi_list)
        
    lst_list = extract_values(live_data.get('LST', []))
    if lst_list:
        mean_lst = sum(lst_list) / len(lst_list)
        
    temp_list = extract_values(live_data.get('temp', []))
    if temp_list:
        mean_temp = sum(temp_list) / len(temp_list)
        
    precip_list = extract_values(live_data.get('precip', []))
    if precip_list:
        total_precip = sum(precip_list)
        
    rh_list = extract_values(live_data.get('RH', []))
    if rh_list:
        mean_rh = sum(rh_list) / len(rh_list)
        
    wind_list = extract_values(live_data.get('wind', []))
    if wind_list:
        mean_wind = sum(wind_list) / len(wind_list)
        
    # Look up SQLite metadata details
    db_path = "data/app.db"
    variety = "CO_265"
    crop_type = "newly_planted"
    irrigation_type = "unknown"
    area = float(live_data.get('field_area_acres') or 3.0)
    n_val = 80.0
    p_val = 40.0
    k_val = 50.0
    veg_interval = 15.0
    rep_interval = 15.0
    
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            try:
                fid = int(farm_id)
            except:
                fid = farm_id
            cursor.execute("""
            SELECT variety, crop_type_clean, irrigation_type, area_acres,
                   n_kg_per_acre, p_kg_per_acre, k_kg_per_acre,
                   irrigation_interval_veg, irrigation_interval_rep
            FROM farms WHERE farm_id = ?
            """, (fid,))
            row = cursor.fetchone()
            conn.close()
            if row:
                variety = row[0] or variety
                crop_type = row[1] or crop_type
                irrigation_type = row[2] or irrigation_type
                area = float(row[3]) if row[3] is not None else area
                n_val = float(row[4]) if row[4] is not None else n_val
                p_val = float(row[5]) if row[5] is not None else p_val
                k_val = float(row[6]) if row[6] is not None else k_val
                veg_interval = float(row[7]) if row[7] is not None else veg_interval
                rep_interval = float(row[8]) if row[8] is not None else rep_interval
        except Exception as e:
            logging.error(f"Error loading farm metadata from SQLite: {e}")
            
    # Form input DataFrame
    input_data = pd.DataFrame([{
        'mean_NDVI': mean_ndvi,
        'max_NDVI': max_ndvi,
        'mean_NDRE': mean_ndre,
        'mean_NDWI': mean_ndwi,
        'mean_LST': mean_lst,
        'mean_temp': mean_temp,
        'total_precip': total_precip,
        'mean_RH': mean_rh,
        'mean_wind': mean_wind,
        'area_acres': area,
        'n_kg_per_acre': n_val,
        'p_kg_per_acre': p_val,
        'k_kg_per_acre': k_val,
        'irrigation_interval_veg': veg_interval,
        'irrigation_interval_rep': rep_interval,
        'variety': variety,
        'crop_type_clean': crop_type,
        'irrigation_type': irrigation_type
    }])
    
    # Predict
    predicted_val = pipeline.predict(input_data)[0]
    predicted_val = float(round(predicted_val, 2))
    
    print(f"Predicted Brix value for Farm {farm_id}: {predicted_val}%")
    
    # Append to intervention plan JSON if requested
    if target_plan_json and os.path.exists(target_plan_json):
        try:
            with open(target_plan_json, 'r') as file_in:
                plan = json.load(file_in)
            plan['predicted_brix'] = predicted_val
            with open(target_plan_json, 'w') as file_out:
                json.dump(plan, file_out, indent=2)
            logging.info(f"Successfully saved predicted_brix = {predicted_val}% to {target_plan_json}")
        except Exception as e:
            logging.error(f"Failed to save predicted brix to plan JSON: {e}")
            
    return predicted_val

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predict Brix sugar content percentages.")
    parser.add_argument("--train", action="store_true", help="Force retrain the RandomForest regression model.")
    parser.add_argument("--predict", action="store_true", help="Perform a Brix prediction for a farm.")
    parser.add_argument("--farm-id", type=str, help="Farm ID to run prediction for.")
    parser.add_argument("-o", "--output", type=str, help="Optionally append predicted brix to this intervention plan JSON file.")
    
    args = parser.parse_args()
    
    if args.train:
        train_model()
    elif args.predict:
        if not args.farm_id:
            print("Error: --farm-id is required for prediction mode.")
            sys.exit(1)
        predict_brix(args.farm_id, args.output)
    else:
        # Train model if not present, otherwise print usage
        if not os.path.exists(MODEL_PATH):
            train_model()
        else:
            parser.print_help()
