import pandas as pd
import numpy as np

def apply_quality_gate(input_path, output_path):
    print(f"Reading cleaned data from {input_path}")
    df = pd.read_csv(input_path)
    
    # Keep only ideal reference farms for curve calculations
    if 'is_ideal' in df.columns:
        df = df[df['is_ideal'] == 1].copy()
        
    initial_rows = len(df)
    
    # Check 1: Incident flag
    df = df[df['incident_flag'] != 1].copy()
    print(f"Rows after dropping incident_flag=1: {len(df)}")
    
    # Check 3: Date completeness
    df = df.dropna(subset=['planting_date', 'harvest_date']).copy()
    print(f"Rows after dropping missing dates: {len(df)}")
    
    # Check 4: Base weight calculation
    df['base_weight'] = df['yield_per_acre']
    
    # Load weights config dynamically
    import json
    import os
    config_path = "data/weights_config.json"
    cfg = {
        "drip_multiplier": 1.2,
        "sprinkler_multiplier": 1.1,
        "newly_planted_multiplier": 1.1,
        "brix_sanity_min": 8.0,
        "brix_sanity_max": 16.0,
        "brix_penalty_multiplier": 0.5
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"Error loading weights config: {e}. Using defaults.")
            
    # Apply user request: Weighted priority to Irrigation and Crop Type
    def irrigation_multiplier(irr_type):
        irr = str(irr_type).lower()
        if 'drip' in irr: return cfg["drip_multiplier"]
        if 'sprinkler' in irr: return cfg["sprinkler_multiplier"]
        return 1.0
        
    def crop_type_multiplier(ctype):
        if str(ctype).lower() == 'newly_planted': return cfg["newly_planted_multiplier"]
        return 1.0
        
    df['irrigation_weight_modifier'] = df['irrigation_type'].apply(irrigation_multiplier)
    df['crop_type_weight_modifier'] = df['crop_type_clean'].apply(crop_type_multiplier)
    
    df['weight'] = df['base_weight'] * df['irrigation_weight_modifier'] * df['crop_type_weight_modifier']
    
    # Check 2: Brix sanity
    brix_min = cfg["brix_sanity_min"]
    brix_max = cfg["brix_sanity_max"]
    brix_penalty = cfg["brix_penalty_multiplier"]
    brix_mask = (df['brix'].notnull()) & ((df['brix'] < brix_min) | (df['brix'] > brix_max))
    df.loc[brix_mask, 'weight'] = df.loc[brix_mask, 'weight'] * brix_penalty
    print(f"Flagged {brix_mask.sum()} rows for Brix sanity check.")
    
    # Normalise weight within variety stratum
    # Note: sum(weight) across the variety will be 1
    df['weight_normalized'] = df.groupby('variety')['weight'].transform(lambda x: x / x.sum())
    
    # Ensure varieties are clean
    df['variety'] = df['variety'].str.strip()
    
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} weighted rows to {output_path} (started with {initial_rows})")

if __name__ == "__main__":
    apply_quality_gate('data/cleaned/farm_data_clean.csv', 'data/cleaned/farm_data_weighted.csv')
