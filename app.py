import os
import sys
import json
import logging
import subprocess
from flask import Flask, request, jsonify, redirect, url_for, session, render_template
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

# Setup logging
os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("data/app.log"),
        logging.StreamHandler(sys.stderr)
    ]
)
app = Flask(__name__, template_folder="frontend/templates", static_folder="frontend/static")
app.secret_key = "secret_session_key_95b227"

# Default credentials (can be overridden via environment variables)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# Helper to check if logged in
def is_logged_in():
    return session.get("logged_in") is True

@app.before_request
def log_request_info():
    if request.path.startswith("/api/") or request.path in ["/login", "/"]:
        logging.info(f"Request: {request.method} {request.path} from {request.remote_addr}")

# --- WEB PAGES ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if is_logged_in():
        return redirect(url_for("index"))
        
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            logging.info("Admin logged in successfully.")
            return redirect(url_for("index"))
        else:
            error = "Invalid username or password."
            logging.warning(f"Failed login attempt for username: {username}")
            
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    logging.info("User logged out.")
    return redirect(url_for("login"))

@app.route("/")
def index():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("index.html")

# --- API ENDPOINTS ---



@app.route("/api/config/varieties", methods=["GET", "POST"])
def config_varieties():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    config_path = "data/ideal_twin/varieties_config.json"
    default_vars = [
        {"variety": "CO_265", "name": "CO_265 (Adsali)", "lifecycle_days": 540, "status": "active", "notes": "Premium Adsali variety with 540-day crop lifecycle."},
        {"variety": "CO_86032", "name": "CO_86032 (Suru)", "lifecycle_days": 420, "status": "active", "notes": "High yield Suru variety with 420-day crop lifecycle."},
        {"variety": "8005", "name": "8005 (Reference)", "lifecycle_days": 420, "status": "active", "notes": "Reference baseline variety with 420-day crop lifecycle."}
    ]
    
    if request.method == "GET":
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return jsonify(json.load(f))
            except Exception as e:
                logging.error(f"Failed to read varieties config: {e}")
        return jsonify(default_vars)
        
    else: # POST
        try:
            req_data = request.json
            variety_code = req_data.get("variety", "").strip().upper().replace(" ", "_")
            if not variety_code:
                return jsonify({"status": "error", "message": "variety code is required"}), 400
                
            # Load existing
            current_list = default_vars
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    current_list = json.load(f)
                    
            # Check if exists, update or append
            found = False
            for v in current_list:
                if v["variety"] == variety_code:
                    v["name"] = req_data.get("name", v.get("name", variety_code))
                    v["lifecycle_days"] = int(req_data.get("lifecycle_days", v.get("lifecycle_days", 420)))
                    v["status"] = req_data.get("status", v.get("status", "draft"))
                    v["notes"] = req_data.get("notes", v.get("notes", ""))
                    found = True
                    break
                    
            if not found:
                current_list.append({
                    "variety": variety_code,
                    "name": req_data.get("name", variety_code),
                    "lifecycle_days": int(req_data.get("lifecycle_days", 420)),
                    "status": req_data.get("status", "draft"),
                    "notes": req_data.get("notes", "")
                })
                
            with open(config_path, 'w') as f:
                json.dump(current_list, f, indent=2)
                
            logging.info(f"Varieties configuration updated for: {variety_code}")
            return jsonify({"status": "success", "varieties": current_list})
        except Exception as e:
            logging.error(f"Failed to save varieties config: {e}")
            return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/ideal-twin/regenerate", methods=["POST"])
def ideal_twin_regenerate():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    logging.info("Initiating Ideal Twin regeneration baseline...")
    logs = []
    
    try:
        # Run step 1 data cleaning
        logging.info("Running Step 1: 01_data_cleaner.py")
        p1 = subprocess.run([sys.executable, "ideal_twin/01_data_cleaner.py"], capture_output=True, text=True)
        logs.append(f"--- 01_data_cleaner.py Output ---\n{p1.stdout}\n{p1.stderr}")
        if p1.returncode != 0:
            raise Exception("Data cleaning script failed.")
            
        # Run step 2 quality gate
        logging.info("Running Step 2: 02_quality_gate.py")
        p2 = subprocess.run([sys.executable, "ideal_twin/02_quality_gate.py"], capture_output=True, text=True)
        logs.append(f"--- 02_quality_gate.py Output ---\n{p2.stdout}\n{p2.stderr}")
        if p2.returncode != 0:
            raise Exception("Quality gate script failed.")
            
        # Run step 4 feature builder
        logging.info("Running Step 4: 04_feature_builder.py")
        p4 = subprocess.run([sys.executable, "ideal_twin/04_feature_builder.py"], capture_output=True, text=True)
        logs.append(f"--- 04_feature_builder.py Output ---\n{p4.stdout}\n{p4.stderr}")
        if p4.returncode != 0:
            raise Exception("Feature builder script failed.")
            
        # Run step 5 ideal twin builder
        logging.info("Running Step 5: 05_ideal_twin_builder.py")
        p5 = subprocess.run([sys.executable, "ideal_twin/05_ideal_twin_builder.py"], capture_output=True, text=True)
        logs.append(f"--- 05_ideal_twin_builder.py Output ---\n{p5.stdout}\n{p5.stderr}")
        if p5.returncode != 0:
            raise Exception("Ideal twin builder script failed.")
        # Run step 6 plotting curves
        logging.info("Running Step 6: 06_plot_curves.py")
        p6 = subprocess.run([sys.executable, "ideal_twin/06_plot_curves.py"], capture_output=True, text=True)
        logs.append(f"--- 06_plot_curves.py Output ---\n{p6.stdout}\n{p6.stderr}")
        if p6.returncode != 0:
            raise Exception("Plotting curves script failed.")
            
        logging.info("Ideal Twin regeneration complete.")
        return jsonify({"status": "success", "logs": "\n\n".join(logs)})
        
    except Exception as e:
        logging.error(f"Ideal Twin regeneration failed: {e}")
        return jsonify({"status": "error", "message": str(e), "logs": "\n\n".join(logs)}), 500

@app.route("/api/farms", methods=["GET"])
def get_farms():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    clean_path = "data/cleaned/farm_data_clean.csv"
    if not os.path.exists(clean_path):
        return jsonify([])
        
    try:
        import pandas as pd
        df = pd.read_csv(clean_path)
        farms = df[['farm_id', 'farmer_name', 'variety']].drop_duplicates().to_dict(orient='records')
        return jsonify(farms)
    except Exception as e:
        logging.error(f"Failed to load farms: {e}")
        return jsonify([])

@app.route("/api/farm/<farm_id>", methods=["GET"])
def get_farm_detail(farm_id):
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    clean_path = "data/cleaned/farm_data_clean.csv"
    coord_path = "data/raw/coordinates.xlsx"
    
    res = {
        "farm_id": farm_id,
        "farmer_name": "",
        "variety": "",
        "area_acres": "",
        "planting_date": "",
        "latitude": "",
        "longitude": ""
    }
    
    import pandas as pd
    import numpy as np
    import os
    
    # 1. Lookup in cleaned CSV
    if os.path.exists(clean_path):
        try:
            df_clean = pd.read_csv(clean_path)
            df_clean['farm_id_str'] = df_clean['farm_id'].dropna().astype(str).str.strip().str.lower()
            match_clean = df_clean[df_clean['farm_id_str'] == str(farm_id).strip().lower()]
            if not match_clean.empty:
                row = match_clean.iloc[0]
                res["farmer_name"] = str(row.get("farmer_name", ""))
                res["variety"] = str(row.get("variety", ""))
                res["area_acres"] = float(row.get("area_acres")) if not pd.isna(row.get("area_acres")) else ""
                
                planting_date_raw = row.get("planting_date", "")
                try:
                    p_dt = pd.to_datetime(planting_date_raw)
                    res["planting_date"] = p_dt.strftime('%d-%m-%Y')
                except:
                    res["planting_date"] = str(planting_date_raw)
        except Exception as e:
            logging.error(f"Error looking up farm in csv: {e}")
            
    # 2. Lookup in Coordinates excel
    if os.path.exists(coord_path):
        try:
            df_coords = pd.read_excel(coord_path, sheet_name='Coordinates')
            df_coords['Farm_id_str'] = df_coords['Farm_id'].dropna().astype(str).str.strip().str.lower()
            match_coords = df_coords[df_coords['Farm_id_str'] == str(farm_id).strip().lower()]
            if not match_coords.empty:
                res["latitude"] = float(match_coords['Lat'].mean())
                res["longitude"] = float(match_coords['Long'].mean())
        except Exception as e:
            logging.error(f"Error looking up coordinates: {e}")
            
    return jsonify(res)

@app.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    import pandas as pd
    import os
    
    clean_path = "data/cleaned/farm_data_clean.csv"
    farms_list = []
    if os.path.exists(clean_path):
        try:
            df = pd.read_csv(clean_path)
            farms_list = df['farm_id'].dropna().unique().tolist()
        except Exception as e:
            logging.error(f"Failed to read clean farm data: {e}")
            
    total_farms = len(farms_list)
    
    healthy_count = 0
    watch_count = 0
    critical_count = 0
    top_risk_list = []
    
    for fid in farms_list:
        safe_name = str(fid).lower().replace(" ", "_")
        plan_path = f"data/gap_reports/{safe_name}_intervention_plan.json"
        
        health = 100
        primary_issue = "Optimal parameters"
        action_required = "Monitor vegetation growth"
        last_updated = "Yesterday"
        
        if os.path.exists(plan_path):
            try:
                with open(plan_path, 'r') as f:
                    plan = json.load(f)
                health = float(plan.get("overall_health_score", 100))
                
                if plan.get("last_observation_date"):
                    last_updated = plan["last_observation_date"]
                else:
                    last_updated = "Today"
                    
                rec_list = plan.get("consolidated_intervention_plan", [])
                if rec_list:
                    rec_list = sorted(rec_list, key=lambda x: x.get("priority_rank", 4))
                    first_rec = rec_list[0]
                    primary_issue = first_rec.get("category", "General Anomaly").upper()
                    
                    deviations = plan.get("deviations", {})
                    red_indices = []
                    for idx_name, dev_list in deviations.items():
                        if dev_list and dev_list[-1].get("severity") == "RED":
                            red_indices.append(idx_name)
                    if red_indices:
                        primary_issue = f"{primary_issue} ({', '.join(red_indices)} RED)"
                    else:
                        primary_issue = f"{primary_issue} (Deviation Alert)"
                    action_required = first_rec.get("intervention", "Scout field")
            except Exception as e:
                logging.error(f"Failed to read plan for {fid}: {e}")
                
        if health >= 75:
            healthy_count += 1
        elif health >= 40:
            watch_count += 1
        else:
            critical_count += 1
            
        top_risk_list.append({
            "farm_id": int(fid) if str(fid).isdigit() else fid,
            "health_score": health,
            "primary_issue": primary_issue,
            "last_updated": last_updated,
            "action_required": action_required
        })
        
    top_risk_list = sorted(top_risk_list, key=lambda x: x["health_score"])
    
    varieties_count = 3
    v_config = "data/ideal_twin/varieties_config.json"
    if os.path.exists(v_config):
        try:
            with open(v_config, 'r') as f:
                v_data = json.load(f)
                varieties_count = len([v for v in v_data if v.get("status") in ["active", "draft"]])
        except Exception as e:
            logging.error(f"Failed to read varieties count: {e}")
            
    return jsonify({
        "total_farms": total_farms,
        "healthy_count": healthy_count,
        "watch_count": watch_count,
        "critical_count": critical_count,
        "varieties_count": varieties_count,
        "top_risk_farms": top_risk_list[:5]
    })

@app.route("/api/ideal-twin/curves", methods=["GET"])
def ideal_twin_curves():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    variety = request.args.get("variety", "8005").strip()
    
    curve_path = f"data/ideal_twin/ideal_twin_{variety}.json"
    if not os.path.exists(curve_path):
        return jsonify({"error": f"No baseline curves available for variety {variety}. Please collect farm features or register crop data first."}), 404
        
    try:
        with open(curve_path, 'r') as f:
            data = json.load(f)
        return jsonify({
            "variety": variety,
            "curves": data.get("curves", {}),
            "growth_stages": data.get("growth_stages", {})
        })
    except Exception as e:
        logging.error(f"Failed to read twin curve {variety}: {e}")
        return jsonify({"error": f"Failed to read twin curve {variety}: {str(e)}"}), 500

def run_baseline_pipeline_async():
    def run():
        import subprocess
        import sys
        try:
            logging.info("Starting background ideal twin baseline recalculation...")
            
            # Step 1: Data cleaner
            logging.info("Running Step 1: 01_data_cleaner.py")
            subprocess.run([sys.executable, "ideal_twin/01_data_cleaner.py"])
            
            # Step 2: Quality gate
            logging.info("Running Step 2: 02_quality_gate.py")
            subprocess.run([sys.executable, "ideal_twin/02_quality_gate.py"])
            
            # Step 4: Feature builder
            logging.info("Running Step 4: 04_feature_builder.py")
            subprocess.run([sys.executable, "ideal_twin/04_feature_builder.py"])
            
            # Step 5: Ideal twin builder
            logging.info("Running Step 5: 05_ideal_twin_builder.py")
            subprocess.run([sys.executable, "ideal_twin/05_ideal_twin_builder.py"])
            
            # Step 6: Plot curves
            logging.info("Running Step 6: 06_plot_curves.py")
            subprocess.run([sys.executable, "ideal_twin/06_plot_curves.py"])
            
            logging.info("Background ideal twin baseline recalculation completed successfully!")
        except Exception as e:
            logging.error(f"Error in background baseline recalculation: {e}")
            
    import threading
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()

def save_farm_to_excel(farm_id, lat, lon, area, variety, planting_date):
    import pandas as pd
    import numpy as np
    import os
    
    # 1. Update Satellite_twin_data.xlsx sheet 'Farmer Data'
    excel_path = "data/raw/Satellite_twin_data.xlsx"
    if os.path.exists(excel_path):
        try:
            xls = pd.ExcelFile(excel_path)
            sheets = {}
            for s_name in xls.sheet_names:
                sheets[s_name] = pd.read_excel(excel_path, sheet_name=s_name)
                
            df_farmer = sheets.get('Farmer Data')
            if df_farmer is not None:
                # check if farm_id already exists, if so delete it to prevent duplicates
                try:
                    fid = int(farm_id)
                    df_farmer = df_farmer[df_farmer['Farm_id'] != fid]
                except:
                    df_farmer = df_farmer[df_farmer['Farm_id'] != farm_id]
                    
                s_no = 1
                if not df_farmer['S.No'].empty:
                    valid_s_nos = pd.to_numeric(df_farmer['S.No'], errors='coerce').dropna()
                    if not valid_s_nos.empty:
                        s_no = int(valid_s_nos.max()) + 1
                
                # Create a new row matching the columns
                new_row = {}
                for col in df_farmer.columns:
                    new_row[col] = np.nan
                    
                # Fill inputs
                new_row['S.No'] = s_no
                new_row['Farm_id'] = int(farm_id) if str(farm_id).isdigit() else farm_id
                
                # infer season year from planting_date (format DD-MM-YYYY)
                try:
                    parts = planting_date.split('-')
                    year = int(parts[2])
                    new_row['Year (वर्ष)'] = f"{year}-{str(year+1)[-2:]}"
                except:
                    new_row['Year (वर्ष)'] = "2025-26"
                    
                new_row['Farmer Name\nशेतकऱ्याचे नाव'] = f"Farm {farm_id} User"
                new_row['Variety\nपिकाची जात'] = variety
                new_row['Newly Planted / Ratoon\nनव्याने लागवड केलेले / खोडवा'] = "Newly Planted"
                new_row['Planting Date \nलागवडीची तारीख'] = pd.to_datetime(planting_date, format='%d-%m-%Y', errors='coerce')
                new_row['Cultivating area (in acres)\nलागवडीचे क्षेत्र (एकरमध्ये)'] = float(area)
                
                df_farmer = pd.concat([df_farmer, pd.DataFrame([new_row])], ignore_index=True)
                sheets['Farmer Data'] = df_farmer
                
            # 2. Update coordinates in Satellite_twin_data.xlsx coordinates sheet
            d_deg = np.sqrt(float(area) * 4047.0) / 2.0 / 111000.0
            new_coords = []
            offsets = [(-1, -1), (-1, 1), (1, 1), (1, -1)]
            for dx, dy in offsets:
                new_coords.append({
                    'Farm_id': int(farm_id) if str(farm_id).isdigit() else farm_id,
                    'Farmer Name\nशेतकऱ्याचे नाव': f"Farm {farm_id}",
                    'Lat': float(lat) + dx * d_deg,
                    'Long': float(lon) + dy * d_deg
                })
                
            df_coords_s = sheets.get('Coordinates')
            if df_coords_s is not None:
                try:
                    fid = int(farm_id)
                    df_coords_s = df_coords_s[df_coords_s['Farm_id'] != fid]
                except:
                    df_coords_s = df_coords_s[df_coords_s['Farm_id'] != farm_id]
                df_coords_s = pd.concat([df_coords_s, pd.DataFrame(new_coords)], ignore_index=True)
                sheets['Coordinates'] = df_coords_s
                
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                for s_name, s_df in sheets.items():
                    s_df.to_excel(writer, sheet_name=s_name, index=False)
            logging.info(f"Successfully saved farm {farm_id} to {excel_path}")
        except Exception as e:
            logging.error(f"Failed to save farm to {excel_path}: {e}")
            
    # 3. Update coordinates.xlsx sheet 'Coordinates'
    coord_path = "data/raw/coordinates.xlsx"
    if os.path.exists(coord_path):
        try:
            xls_c = pd.ExcelFile(coord_path)
            sheets_c = {}
            for s_name in xls_c.sheet_names:
                sheets_c[s_name] = pd.read_excel(coord_path, sheet_name=s_name)
                
            df_coords_c = sheets_c.get('Coordinates')
            if df_coords_c is not None:
                try:
                    fid = int(farm_id)
                    df_coords_c = df_coords_c[df_coords_c['Farm_id'] != fid]
                except:
                    df_coords_c = df_coords_c[df_coords_c['Farm_id'] != farm_id]
                df_coords_c = pd.concat([df_coords_c, pd.DataFrame(new_coords)], ignore_index=True)
                sheets_c['Coordinates'] = df_coords_c
                
            with pd.ExcelWriter(coord_path, engine='openpyxl') as writer:
                for s_name, s_df in sheets_c.items():
                    s_df.to_excel(writer, sheet_name=s_name, index=False)
            logging.info(f"Successfully saved coordinates for farm {farm_id} to {coord_path}")
        except Exception as e:
            logging.error(f"Failed to save coordinates to {coord_path}: {e}")
            
    # 4. Trigger baseline recalculation pipeline in background
    try:
        run_baseline_pipeline_async()
    except Exception as e:
        logging.error(f"Failed to run baseline recalculation pipeline: {e}")

def save_raw_farm_to_excel(record):
    import pandas as pd
    import numpy as np
    import os
    
    farm_id = record.get('farm_id')
    lat = record.get('latitude')
    lon = record.get('longitude')
    area = record.get('area_acres')
    variety = record.get('variety')
    planting_date = record.get('planting_date')
    
    # Auto-register variety in varieties_config.json if missing
    if variety:
        try:
            import json
            config_path = "data/ideal_twin/varieties_config.json"
            v_code = str(variety).strip().upper().replace(" ", "_")
            
            # Load default or existing
            default_vars = [
                {"variety": "CO_265", "name": "CO_265 (Adsali)", "lifecycle_days": 540, "status": "active", "notes": "Premium Adsali variety with 540-day crop lifecycle."},
                {"variety": "CO_86032", "name": "CO_86032 (Suru)", "lifecycle_days": 420, "status": "active", "notes": "High yield Suru variety with 420-day crop lifecycle."},
                {"variety": "8005", "name": "8005 (Reference)", "lifecycle_days": 420, "status": "active", "notes": "Reference baseline variety with 420-day crop lifecycle."}
            ]
            current_list = default_vars
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    current_list = json.load(f)
                    
            if not any(v["variety"] == v_code for v in current_list):
                current_list.append({
                    "variety": v_code,
                    "name": f"{v_code} (Custom)",
                    "lifecycle_days": 420,
                    "status": "active",
                    "notes": f"Auto-registered variety {v_code} from raw farm registration."
                })
                with open(config_path, 'w') as f:
                    json.dump(current_list, f, indent=2)
                logging.info(f"Auto-registered new variety in config: {v_code}")
        except Exception as e:
            logging.error(f"Failed to auto-register variety {variety}: {e}")

    # 1. Update Regular_farmers_data.xlsx
    excel_path = "data/raw/Regular_farmers_data.xlsx"
    template_path = "data/raw/Satellite_twin_data.xlsx"
    
    if not os.path.exists(excel_path) and os.path.exists(template_path):
        try:
            xls_t = pd.ExcelFile(template_path)
            sheets_t = {}
            for s_name in xls_t.sheet_names:
                df_t = pd.read_excel(template_path, sheet_name=s_name)
                sheets_t[s_name] = df_t.iloc[0:0]
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                for s_name, s_df in sheets_t.items():
                    s_df.to_excel(writer, sheet_name=s_name, index=False)
            logging.info(f"Initialized {excel_path} from template structure.")
        except Exception as e:
            logging.error(f"Failed to initialize {excel_path}: {e}")

    if os.path.exists(excel_path):
        try:
            xls = pd.ExcelFile(excel_path)
            sheets = {}
            for s_name in xls.sheet_names:
                sheets[s_name] = pd.read_excel(excel_path, sheet_name=s_name)
                
            df_farmer = sheets.get('Farmer Data')
            if df_farmer is not None:
                # Remove duplicate Farm_id
                try:
                    fid = int(farm_id)
                    df_farmer = df_farmer[df_farmer['Farm_id'] != fid]
                except:
                    df_farmer = df_farmer[df_farmer['Farm_id'] != farm_id]
                    
                s_no = 1
                if not df_farmer['S.No'].empty:
                    valid_s_nos = pd.to_numeric(df_farmer['S.No'], errors='coerce').dropna()
                    if not valid_s_nos.empty:
                        s_no = int(valid_s_nos.max()) + 1
                        
                # Create a new row
                new_row = {}
                for col in df_farmer.columns:
                    new_row[col] = np.nan
                    
                # Helper to map inputs
                def get_col_name(prefix):
                    for col in df_farmer.columns:
                        if str(col).lower().startswith(prefix.lower()):
                            return col
                    for col in df_farmer.columns:
                        if prefix.lower() in str(col).lower():
                            return col
                    return None
                    
                # Fill row fields
                new_row['S.No'] = s_no
                new_row['Farm_id'] = int(farm_id) if str(farm_id).isdigit() else farm_id
                
                # Safe conversions helpers
                def to_float(v):
                    if v is None or str(v).strip() == "":
                        return np.nan
                    try:
                        return float(v)
                    except:
                        return np.nan
                        
                # Mapping dict
                mappings = {
                    'Year': record.get('year'),
                    'Farmer Name': record.get('farmer_name'),
                    'Village': record.get('village'),
                    'Variety': record.get('variety'),
                    'Newly Planted': record.get('crop_type'),
                    'Planting Date': pd.to_datetime(planting_date, format='%d-%m-%Y', errors='coerce') if planting_date else np.nan,
                    'Harvest Date': pd.to_datetime(record.get('harvest_date'), format='%d-%m-%Y', errors='coerce') if record.get('harvest_date') else np.nan,
                    'Cultivating area': to_float(area),
                    'Yield': to_float(record.get('yield_achieved')),
                    'Any untoward incident': record.get('incident'),
                    'Soil Type': record.get('soil_type'),
                    'Land Preparation': record.get('land_prep'),
                    'Total cost': to_float(record.get('total_cost')),
                    'Total revenue': to_float(record.get('total_revenue')),
                    'Irrigation type': record.get('irrigation_type'),
                    'Irrigation interval (vegetative': to_float(record.get('irrigation_interval_veg')),
                    'Fertigation': record.get('fertigation'),
                    'Irrigation interval (Rep': to_float(record.get('irrigation_interval_rep')),
                    'Fertilizer Application': record.get('fertilizer_application'),
                    'PGR': record.get('pgr'),
                    'Micronutrients': record.get('micronutrients'),
                    'SOIL HEALTH': record.get('soil_health'),
                    'HUMIC ACID': record.get('humic_acid'),
                    'MULTI MICRONUTRIENT': record.get('multi_nutrient'),
                    'SEAWEED EXTRACT': record.get('seaweed_extract'),
                    'BIOFERTILIZERS': record.get('biofertilizers'),
                    'BIOCONTOL AGENTS': record.get('biocontrol_agents'),
                    'BIOPESTICIDE': record.get('biopesticide'),
                    'AMINO ACIDS': record.get('amino_acids'),
                    'SPECIAL PRACTICES': record.get('special_practices'),
                    'Brix': to_float(record.get('brix')),
                    'CCS': to_float(record.get('ccs'))
                }
                
                for prefix, val in mappings.items():
                    col_name = get_col_name(prefix)
                    if col_name:
                        new_row[col_name] = val
                        
                df_farmer = pd.concat([df_farmer, pd.DataFrame([new_row])], ignore_index=True)
                sheets['Farmer Data'] = df_farmer
                
            # 2. Coordinates sheet updates (calculate 4 corner buffers)
            d_deg = np.sqrt(float(area) * 4047.0) / 2.0 / 111000.0 if area else 0.001
            new_coords = []
            offsets = [(-1, -1), (-1, 1), (1, 1), (1, -1)]
            for dx, dy in offsets:
                new_coords.append({
                    'Farm_id': int(farm_id) if str(farm_id).isdigit() else farm_id,
                    'Farmer Name\nशेतकऱ्याचे नाव': f"Farm {farm_id}",
                    'Lat': float(lat) + dx * d_deg,
                    'Long': float(lon) + dy * d_deg
                })
                
            df_coords_s = sheets.get('Coordinates')
            if df_coords_s is not None:
                try:
                    fid = int(farm_id)
                    df_coords_s = df_coords_s[df_coords_s['Farm_id'] != fid]
                except:
                    df_coords_s = df_coords_s[df_coords_s['Farm_id'] != farm_id]
                df_coords_s = pd.concat([df_coords_s, pd.DataFrame(new_coords)], ignore_index=True)
                sheets['Coordinates'] = df_coords_s
                
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                for s_name, s_df in sheets.items():
                    s_df.to_excel(writer, sheet_name=s_name, index=False)
            logging.info(f"Successfully saved raw farm {farm_id} to {excel_path}")
        except Exception as e:
            logging.error(f"Failed to save raw farm to {excel_path}: {e}")
            
    # 3. Update coordinates.xlsx sheet 'Coordinates'
    coord_path = "data/raw/coordinates.xlsx"
    if os.path.exists(coord_path):
        try:
            xls_c = pd.ExcelFile(coord_path)
            sheets_c = {}
            for s_name in xls_c.sheet_names:
                sheets_c[s_name] = pd.read_excel(coord_path, sheet_name=s_name)
                
            df_coords_c = sheets_c.get('Coordinates')
            if df_coords_c is not None:
                try:
                    fid = int(farm_id)
                    df_coords_c = df_coords_c[df_coords_c['Farm_id'] != fid]
                except:
                    df_coords_c = df_coords_c[df_coords_c['Farm_id'] != farm_id]
                df_coords_c = pd.concat([df_coords_c, pd.DataFrame(new_coords)], ignore_index=True)
                sheets_c['Coordinates'] = df_coords_c
                
            with pd.ExcelWriter(coord_path, engine='openpyxl') as writer:
                for s_name, s_df in sheets_c.items():
                    s_df.to_excel(writer, sheet_name=s_name, index=False)
            logging.info(f"Successfully saved coordinates for farm {farm_id} to {coord_path}")
        except Exception as e:
            logging.error(f"Failed to save coordinates to {coord_path}: {e}")
            
    # 4. Trigger baseline recalculation pipeline in background
    try:
        run_baseline_pipeline_async()
    except Exception as e:
        logging.error(f"Failed to run baseline recalculation pipeline: {e}")

def auto_pull_live_data_if_needed(farm_id, live_json):
    import pandas as pd
    import numpy as np
    import os
    
    if os.path.exists(live_json):
        return True, None
        
    # Try looking up in Excel coordinates
    coord_path = "data/raw/coordinates.xlsx"
    if not os.path.exists(coord_path):
        return False, "Coordinates registry file coordinates.xlsx not found."
        
    try:
        df_coords = pd.read_excel(coord_path, sheet_name='Coordinates')
        df_coords['Farm_id_str'] = df_coords['Farm_id'].dropna().astype(str).str.strip().str.lower()
        match_coords = df_coords[df_coords['Farm_id_str'] == str(farm_id).strip().lower()]
        if match_coords.empty:
            return False, f"Farm ID {farm_id} coordinates centroid not found in raw Coordinates registry."
            
        lat = match_coords.iloc[0]['Lat']
        lon = match_coords.iloc[0]['Long']
        
        # Look up in cleaned csv for variety, planting_date, area_acres
        clean_path = "data/cleaned/farm_data_clean.csv"
        if not os.path.exists(clean_path):
            return False, "Cleaned database farm_data_clean.csv not found."
            
        df_clean = pd.read_csv(clean_path)
        df_clean['farm_id_str'] = df_clean['farm_id'].dropna().astype(str).str.strip().str.lower()
        match_clean = df_clean[df_clean['farm_id_str'] == str(farm_id).strip().lower()]
        if match_clean.empty:
            return False, f"Farm ID {farm_id} details (variety, planting date) not found in cleaned database."
            
        variety = match_clean.iloc[0]['variety']
        area = match_clean.iloc[0]['area_acres']
        planting_date_raw = match_clean.iloc[0]['planting_date']
        
        # parse planting date
        try:
            p_dt = pd.to_datetime(planting_date_raw)
            planting_date_dmY = p_dt.strftime('%d-%m-%Y')
        except Exception as e:
            return False, f"Invalid planting date format in database: {planting_date_raw}"
            
        # Run GEE pull inline
        logging.info(f"Auto-triggering live GEE pull for {farm_id} at ({lat}, {lon})")
        cmd = [
            sys.executable, "current_twin/pull_live_farm.py",
            "--farm-id", str(farm_id),
            "--lat", str(lat),
            "--lon", str(lon),
            "--area-acres", str(area),
            "--variety", str(variety),
            "--planting-date", planting_date_dmY,
            "-o", live_json
        ]
        
        p = subprocess.run(cmd, capture_output=True, text=True)
        logging.info(f"Auto GEE pull output:\n{p.stdout}\n{p.stderr}")
        if p.returncode != 0:
            return False, f"Live pull script execution failed: {p.stderr}"
            
        return True, None
    except Exception as e:
        return False, f"Error during auto GEE lookup/pull: {str(e)}"

@app.route("/api/raw-farm/add", methods=["POST"])
def raw_farm_add():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        req_data = request.json
        farm_id = str(req_data.get("farm_id", "")).strip()
        lat = str(req_data.get("latitude", "")).strip()
        lon = str(req_data.get("longitude", "")).strip()
        area = str(req_data.get("area_acres", "")).strip()
        variety = str(req_data.get("variety", "")).strip()
        planting_date = str(req_data.get("planting_date", "")).strip()
        
        if not farm_id or not lat or not lon or not area or not variety or not planting_date:
            return jsonify({"status": "error", "message": "General Info fields (Farm ID, Name, Variety, Newly Planted/Ratoon), location centroid, and planting date are required."}), 400
            
        save_raw_farm_to_excel(req_data)
        
        return jsonify({"status": "success", "message": f"Successfully registered raw record and coordinates for farm {farm_id}."})
    except Exception as e:
        logging.error(f"Failed to add raw farm record: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/live-twin/pull", methods=["POST"])
def live_twin_pull():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        req_data = request.json
        farm_id = str(req_data.get("farm_id", "")).strip()
        lat = str(req_data.get("latitude", "")).strip()
        lon = str(req_data.get("longitude", "")).strip()
        area = str(req_data.get("field_area_acres", "")).strip()
        variety = str(req_data.get("variety", "")).strip()
        planting_date = str(req_data.get("planting_date", "")).strip()
        
        if not farm_id or not lat or not lon or not area or not variety or not planting_date:
            return jsonify({"status": "error", "message": "All fields are required."}), 400
            
        # Store directly in the raw Excel files
        save_farm_to_excel(farm_id, lat, lon, area, variety, planting_date)
            
        safe_name = farm_id.lower().replace(" ", "_")
        target_path = f"data/live_farms/{safe_name}_live.json"
        os.makedirs("data/live_farms", exist_ok=True)
        
        logging.info(f"Running GEE live data pull for farm: {farm_id}")
        cmd = [
            sys.executable, "current_twin/pull_live_farm.py",
            "--farm-id", farm_id,
            "--lat", lat,
            "--lon", lon,
            "--area-acres", area,
            "--variety", variety,
            "--planting-date", planting_date,
            "-o", target_path
        ]
        
        p = subprocess.run(cmd, capture_output=True, text=True)
        logging.info(f"GEE pull output:\n{p.stdout}\n{p.stderr}")
        
        if p.returncode != 0:
            return jsonify({"status": "error", "message": "GEE live pull execution failed.", "details": p.stderr}), 500
            
        return jsonify({"status": "success", "message": f"Successfully pulled live details for farm {farm_id}.", "output_path": target_path})
        
    except Exception as e:
        logging.error(f"Live pull failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/live-twin/analyze", methods=["POST"])
def live_twin_analyze():
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        req_data = request.json
        farm_id = str(req_data.get("farm_id", "")).strip()
        variety = str(req_data.get("variety", "")).strip()
        
        if not farm_id or not variety:
            return jsonify({"status": "error", "message": "farm_id and variety are required."}), 400
            
        safe_name = farm_id.lower().replace(" ", "_")
        live_json = f"data/live_farms/{safe_name}_live.json"
        ideal_json = f"data/ideal_twin/ideal_twin_{variety}.json"
        gap_json = f"data/gap_reports/{safe_name}_gap_report.json"
        plan_json = f"data/gap_reports/{safe_name}_intervention_plan.json"
        
        # Check and auto GEE pull if missing
        success, err_msg = auto_pull_live_data_if_needed(farm_id, live_json)
        if not success:
            return jsonify({"status": "error", "message": f"Live data JSON not found, and auto-pull failed: {err_msg} Please trigger a manual GEE pull first."}), 400
            
        if not os.path.exists(ideal_json):
            # If the ideal twin JSON doesn't exist, check if we need to regenerate
            return jsonify({"status": "error", "message": f"No ideal twin benchmark JSON found for variety {variety} at {ideal_json}. Regenerate ideal twin first."}), 400
            
        # Step 1: run gap analysis script
        logging.info(f"Running Gap Analysis for {farm_id}")
        cmd1 = [sys.executable, "current_twin/gap_analysis.py", live_json, ideal_json, "-o", gap_json]
        p1 = subprocess.run(cmd1, capture_output=True, text=True)
        if p1.returncode != 0:
            return jsonify({"status": "error", "message": "Gap Analysis execution failed.", "details": p1.stderr}), 500
            
        # Step 2: run recommendations script
        logging.info(f"Running recommendations engine for {farm_id}")
        cmd2 = [sys.executable, "current_twin/recommendations.py", gap_json]
        p2 = subprocess.run(cmd2, capture_output=True, text=True)
        if p2.returncode != 0:
            return jsonify({"status": "error", "message": "Recommendations engine execution failed.", "details": p2.stderr}), 500
            
        # Step 3: run intervention engine script
        logging.info(f"Running rule integration engine for {farm_id}")
        cmd3 = [sys.executable, "current_twin/intervention_engine.py", gap_json, "-o", plan_json]
        p3 = subprocess.run(cmd3, capture_output=True, text=True)
        if p3.returncode != 0:
            return jsonify({"status": "error", "message": "Intervention rules compilation failed.", "details": p3.stderr}), 500
            
        # Load final intervention plan JSON and return
        with open(plan_json, 'r') as f:
            plan = json.load(f)
            
        return jsonify({"status": "success", "plan": plan})
        
    except Exception as e:
        logging.error(f"Live analysis failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
