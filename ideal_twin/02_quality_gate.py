import pandas as pd
import numpy as np

def apply_quality_gate(input_path, output_path):
    print(f"Reading cleaned data from {input_path}")
    df = pd.read_csv(input_path)
    
    initial_rows = len(df)
    
    # Check 1: Incident flag
    df = df[df['incident_flag'] != 1].copy()
    print(f"Rows after dropping incident_flag=1: {len(df)}")
    
    # Check 3: Date completeness
    df = df.dropna(subset=['planting_date', 'harvest_date']).copy()
    print(f"Rows after dropping missing dates: {len(df)}")
    
    # Check 4: Base weight calculation
    df['base_weight'] = df['yield_per_acre']
    
    # Apply user request: Weighted priority to Irrigation and Crop Type
    def irrigation_multiplier(irr_type):
        irr = str(irr_type).lower()
        if 'drip' in irr: return 1.2
        if 'sprinkler' in irr: return 1.1
        return 1.0
        
    def crop_type_multiplier(ctype):
        if str(ctype).lower() == 'newly_planted': return 1.1
        return 1.0
        
    df['irrigation_weight_modifier'] = df['irrigation_type'].apply(irrigation_multiplier)
    df['crop_type_weight_modifier'] = df['crop_type_clean'].apply(crop_type_multiplier)
    
    df['weight'] = df['base_weight'] * df['irrigation_weight_modifier'] * df['crop_type_weight_modifier']
    
    # Check 2: Brix sanity
    # Flag if brix < 8 or > 16 -> weight x 0.5
    brix_mask = (df['brix'].notnull()) & ((df['brix'] < 8) | (df['brix'] > 16))
    df.loc[brix_mask, 'weight'] = df.loc[brix_mask, 'weight'] * 0.5
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
