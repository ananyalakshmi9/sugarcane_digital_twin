import os
import sys
import json
import argparse
import numpy as np

# Mapping between live farm observation JSON keys and Ideal Twin curves JSON keys
FEATURE_MAPPING = {
    "NDVI": "NDVI",
    "NDRE": "NDRE",
    "NDWI": "NDWI",
    "EVI": "EVI",
    "MSAVI": "MSAVI",
    "SAR": "VH_VV",
    "temp": "temperature_2m",
    "precip": "total_precipitation_sum",
    "RH": "relative_humidity",
    "wind": "wind_speed_10m"
}

FEATURE_DISPLAY_NAMES = {
    "NDVI": "NDVI (Vegetation Index)",
    "NDRE": "NDRE (Red Edge Index)",
    "NDWI": "NDWI (Water Index)",
    "EVI": "EVI (Enhanced Veg Index)",
    "MSAVI": "MSAVI (Soil Adjusted Index)",
    "SAR": "SAR VH/VV Backscatter Ratio",
    "temp": "2m Air Temperature",
    "precip": "Daily Precipitation Sum",
    "RH": "Relative Humidity",
    "wind": "10m Wind Speed"
}

def parse_args():
    parser = argparse.ArgumentParser(description="Run gap analysis comparing a live farm's observations against its Ideal Twin.")
    parser.add_argument("farm_json", type=str, help="Path to the new farm's live observations JSON.")
    parser.add_argument("ideal_json", type=str, help="Path to the variety's Ideal Twin JSON.")
    parser.add_argument("--output-file", "-o", type=str, default=None,
                        help="Path to save the output gap report JSON. Defaults to data/gap_reports/<farm_id>_gap_report.json.")
    return parser.parse_args()

def get_growth_stage(dap_bin, growth_stages):
    """Identify growth stage based on boundaries defined in the ideal twin."""
    for stage, bounds in growth_stages.items():
        if bounds[0] <= dap_bin <= bounds[1]:
            return stage.replace('_', ' ').title()
    return "Late Stage"

def main():
    args = parse_args()
    
    # 1. Load Input Files
    if not os.path.exists(args.farm_json):
        print(f"Error: Farm JSON file not found at {args.farm_json}")
        sys.exit(1)
    if not os.path.exists(args.ideal_json):
        print(f"Error: Ideal Twin JSON file not found at {args.ideal_json}")
        sys.exit(1)
        
    with open(args.farm_json, 'r') as f:
        farm_data = json.load(f)
    with open(args.ideal_json, 'r') as f:
        ideal_data = json.load(f)
        
    # Check variety alignment
    if farm_data.get('variety') != ideal_data.get('variety'):
        print(f"Warning: Farm variety ({farm_data.get('variety')}) does not match "
              f"Ideal Twin variety ({ideal_data.get('variety')}). Proceeding with analysis...")
              
    # Extract metadata
    farm_id = farm_data.get('farm_id', 'unknown_farm')
    variety = farm_data.get('variety', 'unknown_variety')
    planting_date = farm_data.get('planting_date', 'unknown_date')
    current_dap = int(farm_data.get('current_dap', 0))
    last_observation_date = farm_data.get('last_observation_date', 'unknown')
    growth_stages = ideal_data.get('growth_stages', {})
    
    # Determine the maximum bin to evaluate based on current_dap
    # Evaluation goes up to the highest 15-day bin <= current_dap
    max_eval_bin = (current_dap // 15) * 15
    evaluated_bins = sorted([b for b in range(0, max_eval_bin + 1, 15)])
    
    print(f"Running gap analysis for farm '{farm_id}' up to DAP {max_eval_bin} (current DAP: {current_dap})...")
    
    # 2. Run Analysis per Feature
    deviations_table = {}
    critical_flags = []
    urgency_candidates = []
    
    total_bins_evaluated = 0
    green_bins_count = 0
    
    for farm_key, ideal_key in FEATURE_MAPPING.items():
        # Get live observations
        live_obs_list = farm_data.get(farm_key, [])
        live_obs_map = {item['dap_bin']: item['observed'] for item in live_obs_list}
        
        # Get ideal curves
        ideal_curves = ideal_data.get('curves', {})
        ideal_curve = ideal_curves.get(ideal_key, {})
        ideal_daps = ideal_curve.get('dap', [])
        ideal_means = ideal_curve.get('mean', [])
        
        # Standard deviation bounds
        s1u = ideal_curve.get('sigma_1_upper', [])
        s1l = ideal_curve.get('sigma_1_lower', [])
        s2u = ideal_curve.get('sigma_2_upper', [])
        s2l = ideal_curve.get('sigma_2_lower', [])
        
        # Map ideal daps to indices for direct lookup
        ideal_dap_map = {dap: idx for idx, dap in enumerate(ideal_daps)}
        
        feature_report = []
        consecutive_red_count = 0
        max_consecutive_red = 0
        max_deviation_in_red_stretch = 0.0
        
        for dap_bin in evaluated_bins:
            # Check if this bin exists in the Ideal Twin curves
            if dap_bin not in ideal_dap_map:
                continue
                
            total_bins_evaluated += 1
            idx = ideal_dap_map[dap_bin]
            
            ideal_mean = ideal_means[idx]
            observed = live_obs_map.get(dap_bin)
            
            growth_stage = get_growth_stage(dap_bin, growth_stages)
            
            # 2.1 Calculate deviations if observed and ideal exist
            if observed is not None and ideal_mean is not None:
                abs_dev = observed - ideal_mean
                pct_dev = (abs_dev / ideal_mean * 100) if ideal_mean != 0 else 0.0
                
                # Check standard deviation bounds availability
                bounds_exist = (
                    len(s1u) > idx and s1u[idx] is not None and
                    len(s1l) > idx and s1l[idx] is not None and
                    len(s2u) > idx and s2u[idx] is not None and
                    len(s2l) > idx and s2l[idx] is not None
                )
                
                # 2.2 Severity Classification
                if bounds_exist:
                    # Case A: Sigma bounds are available
                    if s1l[idx] <= observed <= s1u[idx]:
                        severity = "GREEN"
                        green_bins_count += 1
                    elif s2l[idx] <= observed <= s2u[idx]:
                        severity = "YELLOW"
                    else:
                        severity = "RED"
                else:
                    # Case B: Fallback logic for reference-only/missing bounds
                    abs_pct = abs(pct_dev)
                    if abs_pct <= 10.0:
                        severity = "GREEN"
                        green_bins_count += 1
                    elif abs_pct <= 20.0:
                        severity = "YELLOW"
                    else:
                        severity = "RED"
            else:
                # Missing observed value or ideal mean is classified as RED
                abs_dev = None
                pct_dev = None
                severity = "RED"
                observed = None
            
            feature_report.append({
                "dap_bin": dap_bin,
                "observed": observed,
                "ideal_mean": ideal_mean,
                "absolute_deviation": abs_dev,
                "percentage_deviation": pct_dev,
                "severity": severity,
                "growth_stage": growth_stage
            })
            
            # Track contiguous RED stretches
            if severity == "RED":
                consecutive_red_count += 1
                max_consecutive_red = max(max_consecutive_red, consecutive_red_count)
                # Assign 50.0% fallback deviation for missing readings to compute urgency
                dev_val = abs(pct_dev) if pct_dev is not None else 50.0
                max_deviation_in_red_stretch = max(max_deviation_in_red_stretch, dev_val)
            else:
                consecutive_red_count = 0
                
        deviations_table[farm_key] = feature_report
        
        # 2.3 Flag persistent stress
        if max_consecutive_red >= 2:
            critical_flags.append(farm_key)
            
        # Calculate urgency score for ranking
        # score = consecutive_red_count_max * max_deviation_in_red_stretch
        if max_consecutive_red > 0:
            urgency_score = max_consecutive_red * max_deviation_in_red_stretch
            urgency_candidates.append({
                "feature": farm_key,
                "consecutive_red_bins": max_consecutive_red,
                "max_percentage_deviation": max_deviation_in_red_stretch,
                "urgency_score": urgency_score
            })
            
    # 3. Overall Health Score (percentage of green bins)
    health_score = (green_bins_count / total_bins_evaluated * 100) if total_bins_evaluated > 0 else 0.0
    
    # 4. Rank Top Urgent Deviations
    # Sort descending by urgency score
    urgency_candidates.sort(key=lambda x: x["urgency_score"], reverse=True)
    top_urgent = urgency_candidates[:3]
    
    # Add textual reasoning to top urgent deviations
    for item in top_urgent:
        feat = item["feature"]
        display_name = FEATURE_DISPLAY_NAMES.get(feat, feat)
        item["feature_display_name"] = display_name
        
        if item["max_percentage_deviation"] == 50.0:
            item["reason"] = f"Critical data gap: {display_name} has missing data for {item['consecutive_red_bins']} consecutive bins."
        else:
            item["reason"] = f"{display_name} shows a persistent deviation from the Ideal Twin mean over {item['consecutive_red_bins']} consecutive bins (max deviation magnitude: {item['max_percentage_deviation']:.1f}%)."
            
    # 5. Compile Output
    gap_report = {
        "farm_id": farm_id,
        "variety": variety,
        "planting_date": planting_date,
        "current_dap": current_dap,
        "last_observation_date": last_observation_date,
        "overall_health_score": round(health_score, 1),
        "analysis_scope": f"up to DAP {max_eval_bin} only — crop still growing",
        "critical_flags": critical_flags,
        "top_urgent_deviations": top_urgent,
        "deviations": deviations_table
    }
    
    # Save Report
    output_path = args.output_file
    if not output_path:
        os.makedirs("data/gap_reports", exist_ok=True)
        safe_name = str(farm_id).lower().replace(" ", "_")
        output_path = f"data/gap_reports/{safe_name}_gap_report.json"
        
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    print(f"Saving gap report payload to: {output_path}")
    try:
        with open(output_path, 'w') as f:
            json.dump(gap_report, f, indent=2)
        print("Success! Gap analysis completed.")
    except Exception as e:
        print(f"Error: Failed to write gap report: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
