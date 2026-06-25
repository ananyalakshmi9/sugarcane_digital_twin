import os
import sys
import json
import logging
import subprocess
from datetime import timedelta
from flask import Flask, request, jsonify, redirect, url_for, session, render_template, make_response
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
app.permanent_session_lifetime = timedelta(minutes=15)

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
            session.permanent = True
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
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

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
        
    db_path = "data/app.db"
    if not os.path.exists(db_path):
        return jsonify([])
        
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT farm_id, farmer_name, variety FROM farms")
        rows = cursor.fetchall()
        conn.close()
        
        farms = []
        for r in rows:
            farms.append({
                "farm_id": r[0],
                "farmer_name": r[1],
                "variety": r[2]
            })
        return jsonify(farms)
    except Exception as e:
        logging.error(f"Failed to load farms from SQLite: {e}")
        return jsonify([])

@app.route("/api/farm/<farm_id>", methods=["GET"])
def get_farm_detail(farm_id):
    if not is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401
        
    res = {
        "farm_id": farm_id,
        "farmer_name": "",
        "variety": "",
        "area_acres": "",
        "planting_date": "",
        "latitude": "",
        "longitude": ""
    }
    
    db_path = "data/app.db"
    if not os.path.exists(db_path):
        return jsonify(res)
        
    try:
        import sqlite3
        import pandas as pd
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Try to parse farm_id as integer
        try:
            f_id_val = int(farm_id)
        except:
            f_id_val = farm_id
            
        # 1. Lookup in farms table
        cursor.execute("SELECT farmer_name, variety, area_acres, planting_date FROM farms WHERE farm_id = ?", (f_id_val,))
        row = cursor.fetchone()
        if row:
            res["farmer_name"] = str(row[0] or "")
            res["variety"] = str(row[1] or "")
            res["area_acres"] = float(row[2]) if row[2] is not None else ""
            
            planting_date_raw = row[3]
            try:
                p_dt = pd.to_datetime(planting_date_raw)
                res["planting_date"] = p_dt.strftime('%d-%m-%Y')
            except:
                res["planting_date"] = str(planting_date_raw or "")
                
        # 2. Lookup average coordinates in coordinates table
        cursor.execute("SELECT AVG(lat), AVG(long) FROM coordinates WHERE farm_id = ?", (f_id_val,))
        coords_row = cursor.fetchone()
        if coords_row and coords_row[0] is not None:
            res["latitude"] = float(coords_row[0])
            res["longitude"] = float(coords_row[1])
            
        # 3. Lookup individual boundary vertices
        cursor.execute("SELECT lat, long FROM coordinates WHERE farm_id = ? ORDER BY vertex_index", (f_id_val,))
        vertices = cursor.fetchall()
        if vertices:
            res["boundary"] = [{"lat": float(v[0]), "lng": float(v[1])} for v in vertices]
            
        conn.close()
    except Exception as e:
        logging.error(f"Error looking up farm detail in SQLite: {e}")
        
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

def save_farm_to_excel(farm_id, lat, lon, area, variety, planting_date, boundary=None):
    import pandas as pd
    import numpy as np
    import os
    
    # 1. Update Satellite_twin_data.xlsx sheet 'Farmer Data'
    excel_path = "data/raw/Satellite_twin_data.xlsx"
    new_coords = []
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
            if boundary and len(boundary) >= 3:
                for pt in boundary:
                    new_coords.append({
                        'Farm_id': int(farm_id) if str(farm_id).isdigit() else farm_id,
                        'Farmer Name\nशेतकऱ्याचे नाव': f"Farm {farm_id}",
                        'Lat': float(pt.get('lat')),
                        'Long': float(pt.get('lng'))
                    })
            else:
                d_deg = np.sqrt(float(area) * 4047.0) / 2.0 / 111000.0 if float(area) > 0 else 0.001
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
            
    # 3.5 Update SQLite database farms and coordinates tables
    try:
        import sqlite3
        db_path = "data/app.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        farm_id_int = int(farm_id) if str(farm_id).isdigit() else 0
        area_acres = float(area) if area else 0.0
        
        # Normalize date
        p_dt = pd.to_datetime(planting_date, format='%d-%m-%Y', errors='coerce')
        if pd.isnull(p_dt):
            p_dt = pd.to_datetime(planting_date, errors='coerce')
        planting_date_clean = p_dt.strftime('%Y-%m-%d') if pd.notnull(p_dt) else None
        
        # Normalize variety
        def normalize_variety(v):
            v = str(v).upper().replace(' ', '_')
            if '0265' in v or '265' in v: return 'CO_265'
            if '86032' in v: return 'CO_86032'
            if '8005' in v: return '8005'
            return v
        variety_normalized = normalize_variety(variety)
        
        # season
        try:
            parts = planting_date.split('-')
            year = int(parts[2])
            season_str = f"{year}-{str(year+1)[-2:]}"
        except:
            season_str = "2025-26"
            
        cursor.execute("DELETE FROM farms WHERE farm_id = ?", (farm_id_int,))
        cursor.execute("""
        INSERT INTO farms (
            farm_id, season, farmer_name, variety, crop_type_clean,
            planting_date, area_acres, is_ideal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (farm_id_int, season_str, f"Farm {farm_id} User", variety_normalized, "newly_planted", planting_date_clean, area_acres, 0))
        
        cursor.execute("DELETE FROM coordinates WHERE farm_id = ?", (farm_id_int,))
        
        new_coords_sqlite = []
        for idx, pt in enumerate(new_coords):
            new_coords_sqlite.append((
                farm_id_int,
                idx,
                float(pt['Lat']),
                float(pt['Long'])
            ))
            
        cursor.executemany("""
        INSERT INTO coordinates (farm_id, vertex_index, lat, long)
        VALUES (?, ?, ?, ?);
        """, new_coords_sqlite)
        
        conn.commit()
        conn.close()
        logging.info(f"Successfully synced regular farm {farm_id} coordinates to SQLite.")
    except Exception as e:
        logging.error(f"Failed to sync regular farm {farm_id} to SQLite: {e}")

    # 4. Trigger baseline recalculation pipeline in background
    try:
        run_baseline_pipeline_async()
    except Exception as e:
        logging.error(f"Failed to run baseline recalculation pipeline: {e}")

def save_raw_farm_to_excel(record):
    import sqlite3
    import pandas as pd
    import numpy as np
    import os
    import re
    
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

    # Normalise variety
    def normalize_variety(v):
        v = str(v).upper().replace(' ', '_')
        if '0265' in v or '265' in v: return 'CO_265'
        if '86032' in v: return 'CO_86032'
        if '8005' in v: return '8005'
        return v
    variety_normalized = normalize_variety(variety)
    
    # Normalise dates
    p_dt = pd.to_datetime(planting_date, errors='coerce')
    planting_date_clean = p_dt.strftime('%Y-%m-%d') if pd.notnull(p_dt) else None
    
    h_dt = pd.to_datetime(record.get('harvest_date'), errors='coerce')
    harvest_date_clean = h_dt.strftime('%Y-%m-%d') if pd.notnull(h_dt) else None
    
    crop_duration_days = int((h_dt - p_dt).days) if pd.notnull(p_dt) and pd.notnull(h_dt) else None
    
    # Area and yields
    area_acres = float(area) if area else 0.0
    yield_tonnes = float(record.get('yield_achieved') or 0.0)
    yield_per_acre = yield_tonnes / area_acres if area_acres > 0 else 0.0
    
    # Irrigation
    irrigation_type = record.get('irrigation_type') or 'unknown'
    irrigation_interval_veg = float(record.get('irrigation_interval_veg') or 15.0)
    irrigation_interval_rep = float(record.get('irrigation_interval_rep') or 15.0)
    
    # Incident
    incident = record.get('incident')
    incident_flag = 1 if incident and str(incident).lower().strip() not in ['no', 'none', 'nan', '0'] else 0
    
    # Brix / CCS
    brix = float(record.get('brix')) if record.get('brix') else None
    
    # Fertilizer application extraction
    fertilizer_application = record.get('fertilizer_application')
    
    def extract_fertilizer_bags(text):
        if not text:
            return 0, 0, 0
        text = str(text).lower()
        
        u_bags = 0
        s_bags = 0
        m_bags = 0
        
        urea_matches = re.findall(r'(\d+)\s*(?:bag)?s?\s*(?:of\s*)?urea', text)
        if urea_matches:
            u_bags = sum(int(m) for m in urea_matches)
            
        ssp_matches = re.findall(r'(\d+)\s*(?:bag)?s?\s*(?:of\s*)?ssp', text)
        if ssp_matches:
            s_bags = sum(int(m) for m in ssp_matches)
            
        mop_matches = re.findall(r'(\d+)\s*(?:bag)?s?\s*(?:of\s*)?(?:mop|potash)', text)
        if mop_matches:
            m_bags = sum(int(m) for m in mop_matches)
            
        if u_bags == 0 and s_bags == 0 and m_bags == 0:
            general_matches = re.findall(r'(\d+)\s*bag', text)
            if general_matches:
                u_bags = sum(int(m) for m in general_matches)
                
        return u_bags, s_bags, m_bags

    urea_bags, ssp_bags, mop_bags = extract_fertilizer_bags(fertilizer_application)
    
    n_kg_total = urea_bags * 20.7
    p_kg_total = ssp_bags * 8.0
    k_kg_total = mop_bags * 30.0
    
    n_kg_per_acre = n_kg_total / area_acres if area_acres > 0 else 0.0
    p_kg_per_acre = p_kg_total / area_acres if area_acres > 0 else 0.0
    k_kg_per_acre = k_kg_total / area_acres if area_acres > 0 else 0.0
    
    # Season inference
    season = record.get('season')
    if not season and p_dt is not None:
        year = p_dt.year
        if p_dt.month > 6:
            season = f"{year}-{str(year+1)[-2:]}"
        else:
            season = f"{year-1}-{str(year)[-2:]}"
    elif not season:
        season = "2023-24"
        
    farm_id_int = int(farm_id) if str(farm_id).isdigit() else 0
    crop_type_clean = 'ratoon' if record.get('crop_type') and 'ratoon' in str(record.get('crop_type')).lower() else 'newly_planted'
    farmer_name = record.get('farmer_name') or f"Farm {farm_id}"
    
    # 1. Update SQLite farms table
    db_path = "data/app.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM farms WHERE farm_id = ?", (farm_id_int,))
    cursor.execute("""
    INSERT INTO farms (
        farm_id, season, farmer_name, variety, crop_type_clean,
        planting_date, harvest_date, crop_duration_days, area_acres,
        yield_tonnes, yield_per_acre, irrigation_type, irrigation_interval_veg,
        irrigation_interval_rep, incident_flag, brix, urea_bags_total,
        ssp_bags_total, mop_bags_total, n_kg_total, p_kg_total, k_kg_total,
        n_kg_per_acre, p_kg_per_acre, k_kg_per_acre, is_ideal
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        farm_id_int, season, farmer_name, variety_normalized, crop_type_clean,
        planting_date_clean, harvest_date_clean, crop_duration_days, area_acres,
        yield_tonnes, yield_per_acre, irrigation_type, irrigation_interval_veg,
        irrigation_interval_rep, incident_flag, brix, urea_bags,
        ssp_bags, mop_bags, n_kg_total, p_kg_total, k_kg_total,
        n_kg_per_acre, p_kg_per_acre, k_kg_per_acre, 0
    ))
    
    # 2. Update SQLite coordinates table (use custom boundary polygon if provided, otherwise generate 4-point buffer)
    boundary = record.get('boundary')
    new_coords = []
    
    if boundary and len(boundary) >= 3:
        for idx, pt in enumerate(boundary):
            new_coords.append((farm_id_int, idx, float(pt.get('lat')), float(pt.get('lng'))))
    else:
        d_deg = np.sqrt(area_acres * 4047.0) / 2.0 / 111000.0 if area_acres > 0 else 0.001
        offsets = [(-1, -1), (-1, 1), (1, 1), (1, -1)]
        for idx, (dx, dy) in enumerate(offsets):
            lat_val = float(lat) + dx * d_deg
            lon_val = float(lon) + dy * d_deg
            new_coords.append((farm_id_int, idx, lat_val, lon_val))
        
    cursor.execute("DELETE FROM coordinates WHERE farm_id = ?", (farm_id_int,))
    cursor.executemany("""
    INSERT INTO coordinates (farm_id, vertex_index, lat, long)
    VALUES (?, ?, ?, ?);
    """, new_coords)
    
    conn.commit()
    conn.close()
    logging.info(f"Successfully saved farm {farm_id} and coordinates to SQLite.")
    
    # 3. Trigger baseline recalculation pipeline in background
    try:
        run_baseline_pipeline_async()
    except Exception as e:
        logging.error(f"Failed to run baseline recalculation pipeline: {e}")

def auto_pull_live_data_if_needed(farm_id, live_json):
    import pandas as pd
    import numpy as np
    import os
    import sqlite3
    import subprocess
    import sys
    
    if os.path.exists(live_json):
        return True, None
        
    db_path = "data/app.db"
    if not os.path.exists(db_path):
        return False, "SQLite database app.db not found."
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Look up coordinates centroid
        # Try to parse farm_id as integer
        try:
            f_id_val = int(farm_id)
        except:
            f_id_val = farm_id
            
        cursor.execute("SELECT AVG(lat), AVG(long) FROM coordinates WHERE farm_id = ?", (f_id_val,))
        coords_row = cursor.fetchone()
        if not coords_row or coords_row[0] is None:
            conn.close()
            return False, f"Farm ID {farm_id} coordinates centroid not found in SQLite registry."
            
        lat = coords_row[0]
        lon = coords_row[1]
        
        # Look up details in farms table
        cursor.execute("SELECT variety, area_acres, planting_date FROM farms WHERE farm_id = ?", (f_id_val,))
        farm_row = cursor.fetchone()
        conn.close()
        
        if not farm_row:
            return False, f"Farm ID {farm_id} details not found in SQLite farms table."
            
        variety = farm_row[0]
        area = farm_row[1]
        planting_date_raw = farm_row[2]
        
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
        
        boundary = req_data.get("boundary")
        
        if not farm_id or not lat or not lon or not area or not variety or not planting_date:
            return jsonify({"status": "error", "message": "All fields are required."}), 400
            
        # Store directly in the raw Excel files and SQLite
        save_farm_to_excel(farm_id, lat, lon, area, variety, planting_date, boundary)
            
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
            
        # Step 4: run Brix predictor script
        logging.info(f"Running Brix predictor for {farm_id}")
        cmd4 = [sys.executable, "current_twin/brix_predictor.py", "--predict", "--farm-id", farm_id, "-o", plan_json]
        p4 = subprocess.run(cmd4, capture_output=True, text=True)
        if p4.returncode != 0:
            logging.error(f"Brix prediction failed: {p4.stderr}")
            
        # Load final intervention plan JSON and return
        with open(plan_json, 'r') as f:
            plan = json.load(f)
            
        return jsonify({"status": "success", "plan": plan})
        
    except Exception as e:
        logging.error(f"Live analysis failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
