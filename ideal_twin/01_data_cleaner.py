import pandas as pd
import numpy as np

def clean_data(input_path, output_path):
    print(f"Reading raw data from {input_path}")
    df = pd.read_excel(input_path)
    
    # Provide a note
    print("NOTE: Pipeline is dynamic. It will process all valid rows provided in the Excel file.")
    
    # We will rename columns using their index or substring matching to be robust against long Hindi names
    cols = df.columns.tolist()
    
    clean_df = pd.DataFrame()
    
    # The prompt mentions seasons: 2022-23, 2023-24, 2024-25. Let's use column 2
    clean_df['farm_id'] = df.iloc[:, 1]
    clean_df['season'] = df.iloc[:, 2]
    clean_df['farmer_name'] = df.iloc[:, 3]
    clean_df['variety'] = df.iloc[:, 5]
    
    def normalize_variety(v):
        v = str(v).upper().replace(' ', '_')
        if '0265' in v: return 'CO_265'
        if '265' in v: return 'CO_265'
        if '86032' in v: return 'CO_86032'
        if '8005' in v: return '8005'
        return v
        
    clean_df['variety'] = clean_df['variety'].apply(normalize_variety)
    
    clean_df['crop_type_clean'] = df.iloc[:, 6].apply(lambda x: 'ratoon' if isinstance(x, str) and 'ratoon' in x.lower() else 'newly_planted')
    
    # Dates
    clean_df['planting_date'] = pd.to_datetime(df.iloc[:, 7], errors='coerce')
    clean_df['harvest_date'] = pd.to_datetime(df.iloc[:, 8], errors='coerce')
    
    clean_df['crop_duration_days'] = (clean_df['harvest_date'] - clean_df['planting_date']).dt.days
    clean_df['area_acres'] = pd.to_numeric(df.iloc[:, 9], errors='coerce').fillna(0)
    clean_df['yield_tonnes'] = pd.to_numeric(df.iloc[:, 10], errors='coerce').fillna(0)
    clean_df['yield_per_acre'] = np.where(clean_df['area_acres'] > 0, clean_df['yield_tonnes'] / clean_df['area_acres'], 0)
    
    # Irrigation
    clean_df['irrigation_type'] = df.iloc[:, 16].fillna('unknown')
    clean_df['irrigation_interval_veg'] = pd.to_numeric(df.iloc[:, 17], errors='coerce').fillna(15)
    clean_df['irrigation_interval_rep'] = pd.to_numeric(df.iloc[:, 19], errors='coerce').fillna(15)
    
    # Incidents - Column 11: "Any untoward incident faced"
    clean_df['incident_flag'] = df.iloc[:, 11].apply(lambda x: 1 if pd.notnull(x) and str(x).lower().strip() not in ['no', 'none', 'nan', '0'] else 0)
    
    # Brix - Column 35
    clean_df['brix'] = pd.to_numeric(df.iloc[:, 35], errors='coerce')
    
    import re

    def extract_total_bags(text):
        if pd.isnull(text):
            return 0
        text = str(text)
        matches = re.findall(r'(\d+)\s*bag', text, re.IGNORECASE)
        if matches:
            return sum(int(m) for m in matches)
        return 0

    # Fertilizer - columns 20, 21, 22 are Urea, SSP, MOP
    clean_df['urea_bags_total'] = df.iloc[:, 20].apply(extract_total_bags)
    clean_df['ssp_bags_total'] = df.iloc[:, 21].apply(extract_total_bags)
    clean_df['mop_bags_total'] = df.iloc[:, 22].apply(extract_total_bags)
    
    clean_df['n_kg_total'] = clean_df['urea_bags_total'] * 20.7
    clean_df['p_kg_total'] = clean_df['ssp_bags_total'] * 8.0
    clean_df['k_kg_total'] = clean_df['mop_bags_total'] * 30.0
    
    # Avoid division by zero
    clean_df['n_kg_per_acre'] = np.where(clean_df['area_acres'] > 0, clean_df['n_kg_total'] / clean_df['area_acres'], 0)
    clean_df['p_kg_per_acre'] = np.where(clean_df['area_acres'] > 0, clean_df['p_kg_total'] / clean_df['area_acres'], 0)
    clean_df['k_kg_per_acre'] = np.where(clean_df['area_acres'] > 0, clean_df['k_kg_total'] / clean_df['area_acres'], 0)

    # Clean farm_id
    clean_df = clean_df[clean_df['farm_id'].notnull()]
    clean_df['farm_id'] = pd.to_numeric(clean_df['farm_id'], errors='coerce').fillna(0).astype(int)
    clean_df = clean_df[clean_df['farm_id'] > 0]
    
    # The prompt mentions seasons: 2022-23, 2023-24, 2024-25. Let's infer season based on planting_date year.
    def infer_season(date):
        if pd.isnull(date): return '2023-24'
        year = date.year
        if date.month > 6:
            return f"{year}-{str(year+1)[-2:]}"
        else:
            return f"{year-1}-{str(year)[-2:]}"
            
    clean_df['season'] = clean_df['planting_date'].apply(infer_season)

    clean_df.to_csv(output_path, index=False)
    print(f"Saved {len(clean_df)} rows to {output_path}")

if __name__ == "__main__":
    clean_data('data/raw/Satellite_twin_data.xlsx', 'data/cleaned/farm_data_clean.csv')
