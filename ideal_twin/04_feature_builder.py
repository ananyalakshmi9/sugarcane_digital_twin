import pandas as pd

def build_features(farm_data_path, gee_data_path, output_path):
    print(f"Reading farm data from {farm_data_path}")
    farm_df = pd.read_csv(farm_data_path)
    
    print(f"Reading GEE indices from {gee_data_path}")
    gee_df = pd.read_csv(gee_data_path)
    
    # Merge on farm_id and season
    merged_df = pd.merge(gee_df, farm_df, on=['farm_id', 'season'], how='inner')
    
    # The prompt says: "Bin all observations into 15-day windows: DAP 0-14 -> bin 0, DAP 15-29 -> bin 15"
    merged_df['dap_bin'] = (merged_df['DAP'] // 15) * 15
    
    merged_df.to_csv(output_path, index=False)
    print(f"Saved {len(merged_df)} feature rows to {output_path}")

if __name__ == "__main__":
    build_features('data/cleaned/farm_data_weighted.csv', 'data/gee_outputs/indices_by_dap.csv', 'data/merged/farm_features.csv')
