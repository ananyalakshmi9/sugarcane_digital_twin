import sqlite3
import pandas as pd
import os

def clean_data():
    db_path = "data/app.db"
    output_path = 'data/cleaned/farm_data_clean.csv'
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
        
    print(f"Reading raw data from SQLite database at {db_path}")
    conn = sqlite3.connect(db_path)
    df_all = pd.read_sql_query("SELECT * FROM farms", conn)
    conn.close()
    
    # Drop primary key id column to match expected schema exactly
    if 'id' in df_all.columns:
        df_all = df_all.drop(columns=['id'])
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df_all.to_csv(output_path, index=False)
    print(f"Saved {len(df_all)} clean rows to {output_path}")

if __name__ == "__main__":
    clean_data()

