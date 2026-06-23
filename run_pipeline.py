import os
import sys
import subprocess
import argparse
import json

def run_baseline_pipeline():
    print("====================================================")
    print("Initiating Ideal Twin Baseline Curve Recalculation")
    print("====================================================\n")
    
    scripts = [
        ("Step 1: Data Cleaner", ["ideal_twin/01_data_cleaner.py"]),
        ("Step 2: Quality Gate", ["ideal_twin/02_quality_gate.py"]),
        ("Step 4: Feature Builder", ["ideal_twin/04_feature_builder.py"]),
        ("Step 5: Ideal Twin Builder", ["ideal_twin/05_ideal_twin_builder.py"]),
        ("Step 6: Plot Curves", ["ideal_twin/06_plot_curves.py"])
    ]
    
    for name, cmd in scripts:
        print(f"Running {name}...")
        p = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
        print(p.stdout)
        if p.stderr:
            print(p.stderr, file=sys.stderr)
        if p.returncode != 0:
            print(f"ERROR: {name} failed. Halting pipeline.", file=sys.stderr)
            sys.exit(p.returncode)
            
    print("====================================================")
    print("Baseline Curves Generated Successfully!")
    print("All outputs have been written to data/ideal_twin/ and data/plots/")
    print("====================================================")

def run_farm_analysis(farm_id, lat, lon, area, variety, planting_date):
    print("====================================================")
    print(f"Running Live Gap Analysis for Farm: {farm_id}")
    print("====================================================\n")
    
    safe_name = str(farm_id).lower().replace(" ", "_")
    live_json = f"data/live_farms/{safe_name}_live.json"
    ideal_json = f"data/ideal_twin/ideal_twin_{variety}.json"
    gap_json = f"data/gap_reports/{safe_name}_gap_report.json"
    plan_json = f"data/gap_reports/{safe_name}_intervention_plan.json"
    
    # Check if ideal twin baseline exists
    if not os.path.exists(ideal_json):
        print(f"ERROR: Ideal Twin curve file not found for variety {variety} at {ideal_json}.")
        print("Please run --baseline recalculation first or select a valid variety.")
        sys.exit(1)
        
    # Step 1: Pull live GEE data
    print("Step 1: Extracting live satellite & weather features from GEE...")
    cmd_pull = [
        sys.executable, "current_twin/pull_live_farm.py",
        "--farm-id", str(farm_id),
        "--lat", str(lat),
        "--lon", str(lon),
        "--area-acres", str(area),
        "--variety", str(variety),
        "--planting-date", str(planting_date),
        "-o", live_json
    ]
    p_pull = subprocess.run(cmd_pull, capture_output=True, text=True)
    print(p_pull.stdout)
    if p_pull.returncode != 0:
        print(f"ERROR: Live GEE extraction failed:\n{p_pull.stderr}", file=sys.stderr)
        sys.exit(p_pull.returncode)
        
    # Step 2: Run gap analysis
    print("Step 2: Performing daily parameter gap alignment...")
    cmd_gap = [sys.executable, "current_twin/gap_analysis.py", live_json, ideal_json, "-o", gap_json]
    p_gap = subprocess.run(cmd_gap, capture_output=True, text=True)
    print(p_gap.stdout)
    if p_gap.returncode != 0:
        print(f"ERROR: Gap Analysis alignment failed:\n{p_gap.stderr}", file=sys.stderr)
        sys.exit(p_gap.returncode)
        
    # Step 3: Run recommendations
    print("Step 3: Evaluating agricultural rules & advisory...")
    cmd_rec = [sys.executable, "current_twin/recommendations.py", gap_json]
    p_rec = subprocess.run(cmd_rec, capture_output=True, text=True)
    print(p_rec.stdout)
    if p_rec.returncode != 0:
        print(f"ERROR: Recommendations generation failed:\n{p_rec.stderr}", file=sys.stderr)
        sys.exit(p_rec.returncode)
        
    # Step 4: Run intervention engine compilation
    print("Step 4: Compiling consolidated action plan checklist...")
    cmd_int = [sys.executable, "current_twin/intervention_engine.py", gap_json, "-o", plan_json]
    p_int = subprocess.run(cmd_int, capture_output=True, text=True)
    print(p_int.stdout)
    if p_int.returncode != 0:
        print(f"ERROR: Intervention engine failed:\n{p_int.stderr}", file=sys.stderr)
        sys.exit(p_int.returncode)
        
    # Read final compiled report and print summary
    if os.path.exists(plan_json):
        with open(plan_json, 'r') as f:
            plan = json.load(f)
        print("\n" + "="*50)
        print("GAP LAB REPORT & CONSOLIDATED INTERVENTION PLAN")
        print("="*50)
        print(f"Farm ID:           {plan.get('farm_id')}")
        print(f"Variety:           {plan.get('variety')}")
        print(f"Planting Date:     {plan.get('planting_date')}")
        print(f"Current DAP:       {plan.get('current_dap')} days")
        print(f"Overall Health:    {plan.get('overall_health_score')}%")
        print("\nAction Plan Recommendations:")
        for item in plan.get('consolidated_intervention_plan', []):
            print(f" [{item.get('priority_rank')}] {item.get('source').upper()} Action (Urgency: {item.get('urgency')}):")
            print(f"     -> {item.get('intervention')}")
        print("="*50)
        print(f"Full report saved to: {plan_json}")
        print("="*50)

def main():
    parser = argparse.ArgumentParser(description="Sugarcane Digital Twin Terminal Runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--baseline", action="store_true", help="Run the Ideal Twin baseline recalculation pipeline.")
    group.add_argument("--analyze", action="store_true", help="Run a single farm gap analysis.")
    
    # Analysis options
    parser.add_argument("--farm-id", type=str, help="Farm ID or name (required for --analyze).")
    parser.add_argument("--lat", type=float, help="Centroid latitude (required for --analyze).")
    parser.add_argument("--lon", type=float, help="Centroid longitude (required for --analyze).")
    parser.add_argument("--area", type=float, help="Field area in acres (required for --analyze).")
    parser.add_argument("--variety", type=str, choices=["CO_265", "CO_86032", "8005"], help="Crop variety (required for --analyze).")
    parser.add_argument("--planting-date", type=str, help="Planting date in DD-MM-YYYY format (required for --analyze).")
    
    args = parser.parse_args()
    
    if args.baseline:
        run_baseline_pipeline()
    elif args.analyze:
        if not all([args.farm_id, args.lat, args.lon, args.area, args.variety, args.planting_date]):
            parser.error("--analyze requires --farm-id, --lat, --lon, --area, --variety, and --planting-date.")
        run_farm_analysis(args.farm_id, args.lat, args.lon, args.area, args.variety, args.planting_date)

if __name__ == "__main__":
    main()
