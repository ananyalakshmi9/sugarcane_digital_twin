import pandas as pd
import numpy as np
import json
import datetime
from scipy.signal import savgol_filter
import os

def build_ideal_twin(input_path, output_dir):
    print(f"Reading features from {input_path}")
    df = pd.read_csv(input_path)
    
    os.makedirs(output_dir, exist_ok=True)
    
    indices = ["NDVI", "NDRE", "NDWI", "EVI", "MSAVI", "VH_VV", "temperature_2m", "total_precipitation_sum", "relative_humidity", "wind_speed_10m"]
    
    for variety, stratum_df in df.groupby('variety'):
        # Farm-level Level 1
        farm_curves = {}
        farm_weights = {}
        
        n_farm_seasons = len(stratum_df[['farm_id', 'season']].drop_duplicates())
        unique_farms = stratum_df['farm_id'].unique()
        n_farms = len(unique_farms)
        
        for farm_id, farm_df in stratum_df.groupby('farm_id'):
            # Best yield across seasons for Level 2 weight
            farm_weights[farm_id] = farm_df['yield_per_acre'].max()
            
            # Level 1 weighted mean per DAP bin
            dap_bins = farm_df['dap_bin'].unique()
            dap_bins.sort()
            
            f_curve = {idx: {} for idx in indices}
            for dap in dap_bins:
                bin_df = farm_df[farm_df['dap_bin'] == dap]
                if len(bin_df) == 0: continue
                
                weights = bin_df['weight'].values
                if weights.sum() == 0:
                    weights = np.ones(len(weights))
                    
                for idx in indices:
                    f_curve[idx][dap] = np.average(bin_df[idx].values, weights=weights)
                    
            farm_curves[farm_id] = f_curve
            
        # Level 2 cross-farm aggregation
        all_daps = sorted(stratum_df['dap_bin'].unique())
        ideal_curves = {idx: {'mean': [], 'sigma': [], 'dap': [], 'n_obs': []} for idx in indices}
        
        for dap in all_daps:
            farm_vals = {idx: [] for idx in indices}
            contrib_weights = []
            
            for farm_id in unique_farms:
                if dap in farm_curves[farm_id]['NDVI']:
                    w = farm_weights[farm_id]
                    contrib_weights.append(w)
                    for idx in indices:
                        farm_vals[idx].append(farm_curves[farm_id][idx][dap])
            
            if sum(contrib_weights) == 0:
                continue
                
            for idx in indices:
                mean_val = np.average(farm_vals[idx], weights=contrib_weights)
                std_val = np.std(farm_vals[idx]) if len(farm_vals[idx]) > 1 else 0
                
                ideal_curves[idx]['dap'].append(int(dap))
                ideal_curves[idx]['mean'].append(float(mean_val))
                ideal_curves[idx]['sigma'].append(float(std_val))
                ideal_curves[idx]['n_obs'].append(len(farm_vals[idx]))
                
        # Smoothing and JSON assembly
        reference_only = bool(n_farms < 3)
        
        json_curves = {}
        for idx in indices:
            y_mean = np.array(ideal_curves[idx]['mean'])
            y_sigma = np.array(ideal_curves[idx]['sigma'])
            daps = ideal_curves[idx]['dap']
            n_obs = ideal_curves[idx]['n_obs']
            
            # Interpolate NaNs in y_mean for smoothing
            mask = np.isnan(y_mean)
            if mask.any():
                # If all are NaNs, skip smoothing
                if mask.all():
                    y_mean_interp = y_mean
                else:
                    valid = ~mask
                    y_mean_interp = np.interp(np.arange(len(y_mean)), np.arange(len(y_mean))[valid], y_mean[valid])
            else:
                y_mean_interp = y_mean
            
            # Interpolate NaNs in y_sigma
            mask_sig = np.isnan(y_sigma)
            if mask_sig.any():
                if mask_sig.all():
                    y_sigma_interp = np.zeros_like(y_sigma)
                else:
                    valid_sig = ~mask_sig
                    y_sigma_interp = np.interp(np.arange(len(y_sigma)), np.arange(len(y_sigma))[valid_sig], y_sigma[valid_sig])
            else:
                y_sigma_interp = y_sigma
            
            # Apply Savitzky-Golay if length >= 5
            if len(y_mean_interp) >= 5 and not mask.all():
                y_smooth = savgol_filter(y_mean_interp, window_length=5, polyorder=2)
                smoothed = True
            else:
                y_smooth = y_mean_interp
                smoothed = False
                
            if reference_only or mask.all():
                sig1u = [None] * len(y_smooth)
                sig1l = [None] * len(y_smooth)
                sig2u = [None] * len(y_smooth)
                sig2l = [None] * len(y_smooth)
            else:
                sig1u = (y_smooth + y_sigma_interp).tolist()
                sig1l = (y_smooth - y_sigma_interp).tolist()
                sig2u = (y_smooth + 2*y_sigma_interp).tolist()
                sig2l = (y_smooth - 2*y_sigma_interp).tolist()
                
            # Replace NaNs with None for JSON serialization
            y_smooth_list = [None if np.isnan(v) else v for v in y_smooth.tolist()]
            
            json_curves[idx] = {
                "dap": daps,
                "mean": y_smooth_list,
                "sigma_1_upper": [None if v is None or np.isnan(v) else v for v in sig1u],
                "sigma_1_lower": [None if v is None or np.isnan(v) else v for v in sig1l],
                "sigma_2_upper": [None if v is None or np.isnan(v) else v for v in sig2u],
                "sigma_2_lower": [None if v is None or np.isnan(v) else v for v in sig2l],
                "smoothed": smoothed,
                "n_observations": n_obs
            }
            
        # Agronomic Metadata
        metadata = {
            "mean_yield_per_acre": float(stratum_df['yield_per_acre'].mean()),
            "mean_n_kg_per_acre": float(stratum_df['n_kg_per_acre'].mean()),
            "mean_p_kg_per_acre": float(stratum_df['p_kg_per_acre'].mean()),
            "mean_k_kg_per_acre": float(stratum_df['k_kg_per_acre'].mean()),
            "dominant_irrigation": stratum_df['irrigation_type'].mode()[0] if len(stratum_df) > 0 else "unknown",
            "crop_duration_days_avg": float(stratum_df['crop_duration_days'].mean())
        }
        
        quality_notes = [
            f"{n_farm_seasons} farm-seasons contributed to this stratum"
        ]
        if reference_only:
            quality_notes.append("Fewer than 3 farms contributed, setting as reference only with no sigma bounds")
            
        output_data = {
            "stratum": str(variety),
            "variety": str(variety),
            "n_farms": int(n_farms),
            "n_farm_seasons": int(n_farm_seasons),
            "reference_only": reference_only,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "growth_stages": {
                "germination":  [0, 30],
                "tillering":    [31, 90],
                "grand_growth": [91, 210],
                "maturation":   [211, 300],
                "ripening":     [301, 360]
            },
            "indices": indices,
            "curves": json_curves,
            "agronomic_metadata": metadata,
            "quality_notes": quality_notes
        }
        
        out_file = os.path.join(output_dir, f"ideal_twin_{variety.replace(' ', '_')}.json")
        with open(out_file, 'w') as f:
            json.dump(output_data, f, indent=2)
            
        print(f"Generated {out_file} for stratum {variety}")

if __name__ == "__main__":
    build_ideal_twin('data/merged/farm_features.csv', 'data/ideal_twin')
