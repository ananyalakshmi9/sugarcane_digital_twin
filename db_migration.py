import os
import sqlite3
import pandas as pd
import numpy as np
import re

DB_PATH = "data/app.db"
IDEAL_EXCEL = "data/raw/Satellite_twin_data.xlsx"
REGULAR_EXCEL = "data/raw/Regular_farmers_data.xlsx"
COORD_EXCEL = "data/raw/coordinates.xlsx"

def create_schema(conn):
    cursor = conn.cursor()
    
    # 1. Create farms table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS farms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_id INTEGER,
        season TEXT,
        farmer_name TEXT,
        variety TEXT,
        crop_type_clean TEXT,
        planting_date TEXT,
        harvest_date TEXT,
        crop_duration_days INTEGER,
        area_acres REAL,
        yield_tonnes REAL,
        yield_per_acre REAL,
        irrigation_type TEXT,
        irrigation_interval_veg REAL,
        irrigation_interval_rep REAL,
        incident_flag INTEGER,
        brix REAL,
        urea_bags_total INTEGER,
        ssp_bags_total INTEGER,
        mop_bags_total INTEGER,
        n_kg_total REAL,
        p_kg_total REAL,
        k_kg_total REAL,
        n_kg_per_acre REAL,
        p_kg_per_acre REAL,
        k_kg_per_acre REAL,
        is_ideal INTEGER
    );
    """)
    
    # 2. Create coordinates table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coordinates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        farm_id INTEGER,
        vertex_index INTEGER,
        lat REAL,
        long REAL
    );
    """)
    
    conn.commit()

def extract_total_bags(text):
    if pd.isnull(text):
        return 0
    text = str(text)
    matches = re.findall(r'(\d+)\s*bag', text, re.IGNORECASE)
    if matches:
        return sum(int(m) for m in matches)
    return 0

def normalize_variety(v):
    v = str(v).upper().replace(' ', '_')
    if '0265' in v or '265' in v: return 'CO_265'
    if '86032' in v: return 'CO_86032'
    if '8005' in v: return '8005'
    return v

def clean_excel_to_records(path, is_ideal):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return []
        
    df = pd.read_excel(path)
    records = []
    
    for idx, row in df.iterrows():
        # Get raw farm id
        f_id_raw = row.iloc[1]
        if pd.isnull(f_id_raw):
            continue
        try:
            farm_id = int(float(f_id_raw))
        except:
            continue
            
        if farm_id <= 0:
            continue
            
        season = row.iloc[2]
        farmer_name = str(row.iloc[3])
        variety = normalize_variety(row.iloc[5])
        crop_type_clean = 'ratoon' if isinstance(row.iloc[6], str) and 'ratoon' in row.iloc[6].lower() else 'newly_planted'
        
        planting_date_raw = pd.to_datetime(row.iloc[7], errors='coerce')
        harvest_date_raw = pd.to_datetime(row.iloc[8], errors='coerce')
        
        planting_date = planting_date_raw.strftime('%Y-%m-%d') if pd.notnull(planting_date_raw) else None
        harvest_date = harvest_date_raw.strftime('%Y-%m-%d') if pd.notnull(harvest_date_raw) else None
        
        crop_duration_days = int((harvest_date_raw - planting_date_raw).days) if pd.notnull(planting_date_raw) and pd.notnull(harvest_date_raw) else None
        area_acres = float(pd.to_numeric(row.iloc[9], errors='coerce') or 0.0)
        yield_tonnes = float(pd.to_numeric(row.iloc[10], errors='coerce') or 0.0)
        yield_per_acre = yield_tonnes / area_acres if area_acres > 0 else 0.0
        
        irrigation_type = str(row.iloc[16]) if pd.notnull(row.iloc[16]) else 'unknown'
        irrigation_interval_veg = float(pd.to_numeric(row.iloc[17], errors='coerce') or 15.0)
        irrigation_interval_rep = float(pd.to_numeric(row.iloc[19], errors='coerce') or 15.0)
        
        incident_flag = 1 if pd.notnull(row.iloc[11]) and str(row.iloc[11]).lower().strip() not in ['no', 'none', 'nan', '0'] else 0
        brix = float(pd.to_numeric(row.iloc[35], errors='coerce')) if pd.notnull(row.iloc[35]) and not pd.isna(pd.to_numeric(row.iloc[35], errors='coerce')) else None
        
        urea_bags_total = extract_total_bags(row.iloc[20])
        ssp_bags_total = extract_total_bags(row.iloc[21])
        mop_bags_total = extract_total_bags(row.iloc[22])
        
        n_kg_total = urea_bags_total * 20.7
        p_kg_total = ssp_bags_total * 8.0
        k_kg_total = mop_bags_total * 30.0
        
        n_kg_per_acre = n_kg_total / area_acres if area_acres > 0 else 0.0
        p_kg_per_acre = p_kg_total / area_acres if area_acres > 0 else 0.0
        k_kg_per_acre = k_kg_total / area_acres if area_acres > 0 else 0.0
        
        # Handle season inference if null
        if pd.isnull(season) and planting_date_raw is not None:
            year = planting_date_raw.year
            if planting_date_raw.month > 6:
                season = f"{year}-{str(year+1)[-2:]}"
            else:
                season = f"{year-1}-{str(year)[-2:]}"
        elif pd.isnull(season):
            season = "2023-24"
            
        records.append((
            farm_id, str(season), farmer_name, variety, crop_type_clean,
            planting_date, harvest_date, crop_duration_days, area_acres,
            yield_tonnes, yield_per_acre, irrigation_type, irrigation_interval_veg,
            irrigation_interval_rep, incident_flag, brix, urea_bags_total,
            ssp_bags_total, mop_bags_total, n_kg_total, p_kg_total, k_kg_total,
            n_kg_per_acre, p_kg_per_acre, k_kg_per_acre, int(is_ideal)
        ))
        
    return records

def import_coordinates(conn, path):
    if not os.path.exists(path):
        print(f"Coordinates file not found at {path}")
        return
        
    df = pd.read_excel(path, sheet_name='Coordinates')
    df['Farm_id'] = df['Farm_id'].ffill()
    df = df.dropna(subset=['Lat', 'Long'])
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM coordinates") # Clear existing
    
    # Store indices for farm IDs
    farm_indices = {}
    count = 0
    for idx, row in df.iterrows():
        try:
            farm_id = int(float(row['Farm_id']))
        except:
            continue
            
        if farm_id not in farm_indices:
            farm_indices[farm_id] = 0
        idx_vertex = farm_indices[farm_id]
        farm_indices[farm_id] += 1
        
        lat = float(row['Lat'])
        lon = float(row['Long'])
        
        cursor.execute("""
        INSERT INTO coordinates (farm_id, vertex_index, lat, long)
        VALUES (?, ?, ?, ?);
        """, (farm_id, idx_vertex, lat, lon))
        count += 1
        
    conn.commit()
    print(f"Imported {count} coordinate vertices.")

def run_migration():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    
    print("Creating tables...")
    create_schema(conn)
    
    # Clear existing farms
    cursor = conn.cursor()
    cursor.execute("DELETE FROM farms;")
    conn.commit()
    
    # 1. Load Ideal Twin data
    print("Importing ideal reference farms from Excel...")
    ideal_records = clean_excel_to_records(IDEAL_EXCEL, is_ideal=1)
    print(f"Found {len(ideal_records)} ideal records.")
    
    # 2. Load Regular farmers data
    print("Importing regular farms from Excel...")
    regular_records = clean_excel_to_records(REGULAR_EXCEL, is_ideal=0)
    print(f"Found {len(regular_records)} regular records.")
    
    all_records = ideal_records + regular_records
    
    cursor.executemany("""
    INSERT INTO farms (
        farm_id, season, farmer_name, variety, crop_type_clean,
        planting_date, harvest_date, crop_duration_days, area_acres,
        yield_tonnes, yield_per_acre, irrigation_type, irrigation_interval_veg,
        irrigation_interval_rep, incident_flag, brix, urea_bags_total,
        ssp_bags_total, mop_bags_total, n_kg_total, p_kg_total, k_kg_total,
        n_kg_per_acre, p_kg_per_acre, k_kg_per_acre, is_ideal
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, all_records)
    
    conn.commit()
    print(f"Imported {len(all_records)} total farm records into SQLite database.")
    
    # 3. Import Coordinates
    print("Importing coordinates...")
    import_coordinates(conn, COORD_EXCEL)
    
    conn.close()
    print("Migration finished successfully!")

if __name__ == "__main__":
    run_migration()
