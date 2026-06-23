import os
import sys
import json
import argparse
import datetime
import numpy as np
import ee
from dotenv import load_dotenv

def parse_args():
    parser = argparse.ArgumentParser(description="Pull live GEE and weather data for a single new farm.")
    
    # Accept a positional argument which can be a JSON configuration file path
    parser.add_argument("input_json", nargs="?", default=None,
                        help="Path to an input JSON file containing farm details. If provided, CLI options are ignored.")
    
    # Fallback CLI flags
    parser.add_argument("--farm-id", type=str, help="User-defined farm name or ID.")
    parser.add_argument("--lat", "--latitude", type=float, help="Centroid latitude of the farm.")
    parser.add_argument("--lon", "--longitude", type=float, help="Centroid longitude of the farm.")
    parser.add_argument("--area-acres", "--field-area-acres", type=float, help="Field area in acres.")
    parser.add_argument("--variety", type=str, choices=["CO_265", "CO_86032", "8005"],
                        help="Sugarcane variety.")
    parser.add_argument("--planting-date", type=str,
                        help="Planting date in DD-MM-YYYY format.")
    parser.add_argument("--output-file", "-o", type=str, default=None,
                        help="Path to write the output JSON. Defaults to <farm_id>_live.json if not specified.")
    
    return parser.parse_args()

def load_inputs(args):
    """Load and validate inputs from JSON file or CLI flags."""
    farm_id = None
    lat = None
    lon = None
    area_acres = None
    variety = None
    planting_date_str = None
    output_file = None
    
    if args.input_json:
        # Load from JSON file
        print(f"Reading input farm details from JSON file: {args.input_json}")
        if not os.path.exists(args.input_json):
            print(f"Error: JSON file not found at {args.input_json}")
            sys.exit(1)
            
        with open(args.input_json, 'r') as f:
            config = json.load(f)
            
        farm_id = config.get('farm_id')
        lat = config.get('latitude', config.get('lat'))
        lon = config.get('longitude', config.get('lon'))
        area_acres = config.get('field_area_acres', config.get('area_acres'))
        variety = config.get('variety')
        planting_date_str = config.get('planting_date')
        output_file = config.get('output_file') or args.output_file
    else:
        # Load from CLI flags
        farm_id = args.farm_id
        lat = args.lat
        lon = args.lon
        area_acres = args.area_acres
        variety = args.variety
        planting_date_str = args.planting_date
        output_file = args.output_file

    # Basic validations
    errors = []
    if not farm_id:
        errors.append("farm_id is required (use --farm-id or specify in JSON)")
    if lat is None:
        errors.append("latitude (lat) is required")
    else:
        try:
            lat = float(lat)
            if not (-90 <= lat <= 90):
                errors.append(f"latitude {lat} must be between -90 and 90")
        except ValueError:
            errors.append("latitude must be a numeric value")
            
    if lon is None:
        errors.append("longitude (lon) is required")
    else:
        try:
            lon = float(lon)
            if not (-180 <= lon <= 180):
                errors.append(f"longitude {lon} must be between -180 and 180")
        except ValueError:
            errors.append("longitude must be a numeric value")
            
    if area_acres is None:
        errors.append("area_acres is required")
    else:
        try:
            area_acres = float(area_acres)
            if area_acres <= 0:
                errors.append("area_acres must be greater than zero")
        except ValueError:
            errors.append("area_acres must be a numeric value")
            
    if not variety or variety not in ["CO_265", "CO_86032", "8005"]:
        errors.append("variety must be one of: CO_265, CO_86032, 8005")
        
    planting_date = None
    if not planting_date_str:
        errors.append("planting_date is required (format: DD-MM-YYYY)")
    else:
        try:
            planting_date = datetime.datetime.strptime(planting_date_str, "%d-%m-%Y").date()
            if planting_date > datetime.date.today():
                errors.append(f"planting_date {planting_date_str} cannot be in the future")
        except ValueError:
            errors.append(f"planting_date '{planting_date_str}' is invalid, must be in DD-MM-YYYY format")
            
    if errors:
        print("Input validation failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
        
    if not output_file:
        # Default output filename
        safe_name = str(farm_id).lower().replace(" ", "_")
        output_file = f"{safe_name}_live.json"
        
    return {
        "farm_id": str(farm_id),
        "latitude": lat,
        "longitude": lon,
        "field_area_acres": area_acres,
        "variety": variety,
        "planting_date": planting_date,
        "planting_date_str": planting_date_str,
        "output_file": output_file
    }

def calculate_buffer_radius(acres):
    """Calculate circle radius in meters corresponding to acreage area."""
    area_sq_m = acres * 4046.85642
    radius = (area_sq_m / np.pi) ** 0.5
    return radius

def main():
    load_dotenv()
    args = parse_args()
    farm = load_inputs(args)
    
    # 1. Initialize Google Earth Engine
    project_id = os.getenv("GEE_PROJECT_ID", "harvest-maximizer")
    print(f"Initializing Google Earth Engine (project='{project_id}')...")
    try:
        ee.Initialize(project=project_id)
    except Exception as e:
        print(f"GEE Initialization failed: {e}")
        print("Please authenticate using 'gcloud auth application-default login' or 'earthengine authenticate'")
        sys.exit(1)
        
    # 2. Setup geometries
    radius = calculate_buffer_radius(farm['field_area_acres'])
    print(f"Calculated circular buffer radius: {radius:.2f} meters for {farm['field_area_acres']} acres.")
    
    centroid = ee.Geometry.Point([farm['longitude'], farm['latitude']])
    roi = centroid.buffer(radius)
    
    # 3. Query ranges
    # GEE filterDate end is exclusive, so query until tomorrow to capture all available data up to today
    p_date_str = farm['planting_date'].strftime('%Y-%m-%d')
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    end_date_str = tomorrow.strftime('%Y-%m-%d')
    
    print(f"Querying observations from {p_date_str} to {datetime.date.today().strftime('%Y-%m-%d')}...")
    
    # Dictionary to hold raw timeseries data points
    raw_data = {
        "NDVI": [], "NDRE": [], "NDWI": [], "EVI": [], "MSAVI": [],
        "SAR": [], "temp": [], "precip": [], "RH": [], "wind": []
    }
    
    # --- A. Sentinel-2 L2A ---
    print("Fetching Sentinel-2 multispectral imagery...")
    def add_s2_indices(image):
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        ndre = image.normalizedDifference(['B8', 'B5']).rename('NDRE')
        ndwi = image.normalizedDifference(['B8', 'B11']).rename('NDWI')
        evi = image.expression(
            '2.5 * ((N - R) / (N + 6 * R - 7.5 * B + 1))', {
                'N': image.select('B8').divide(10000),
                'R': image.select('B4').divide(10000),
                'B': image.select('B2').divide(10000)
            }).rename('EVI')
        msavi = image.expression(
            '(2 * N + 1 - sqrt(pow((2 * N + 1), 2) - 8 * (N - R))) / 2', {
                'N': image.select('B8').divide(10000),
                'R': image.select('B4').divide(10000)
            }).rename('MSAVI')
        return image.addBands([ndvi, ndre, ndwi, evi, msavi])

    s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterBounds(roi) \
        .filterDate(p_date_str, end_date_str) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
        .map(add_s2_indices)
        
    def get_s2_stats(image):
        date = image.date().format('YYYY-MM-dd')
        stats = image.select(['NDVI', 'NDRE', 'NDWI', 'EVI', 'MSAVI']).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=10, maxPixels=1e9)
        return ee.Feature(None, stats).set('date', date)
        
    try:
        s2_features = ee.FeatureCollection(s2.map(get_s2_stats)).getInfo()['features']
        print(f"  Found {len(s2_features)} Sentinel-2 scenes.")
        for feat in s2_features:
            props = feat['properties']
            obs_date = props.get('date')
            if obs_date and props.get('NDVI') is not None:
                dap = (datetime.datetime.strptime(obs_date, "%Y-%m-%d").date() - farm['planting_date']).days
                if dap >= 0:
                    for key in ["NDVI", "NDRE", "NDWI", "EVI", "MSAVI"]:
                        raw_data[key].append((obs_date, dap, props.get(key)))
    except Exception as e:
        print(f"  Warning: Sentinel-2 query failed: {e}")
        
    # --- B. Sentinel-1 GRD ---
    print("Fetching Sentinel-1 SAR backscatter...")
    s1 = ee.ImageCollection('COPERNICUS/S1_GRD') \
        .filterBounds(roi) \
        .filterDate(p_date_str, end_date_str) \
        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
        .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING')) \
        .select(['VH', 'VV'])
        
    def get_s1_stats(image):
        vh_lin = ee.Image(10.0).pow(image.select('VH').divide(10.0))
        vv_lin = ee.Image(10.0).pow(image.select('VV').divide(10.0))
        vh_vv = vh_lin.divide(vv_lin).rename('VH_VV')
        
        date = image.date().format('YYYY-MM-dd')
        stats = vh_vv.reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=10, maxPixels=1e9)
        return ee.Feature(None, stats).set('date', date)
        
    try:
        s1_features = ee.FeatureCollection(s1.map(get_s1_stats)).getInfo()['features']
        print(f"  Found {len(s1_features)} Sentinel-1 acquisitions.")
        for feat in s1_features:
            props = feat['properties']
            obs_date = props.get('date')
            if obs_date and props.get('VH_VV') is not None:
                dap = (datetime.datetime.strptime(obs_date, "%Y-%m-%d").date() - farm['planting_date']).days
                if dap >= 0:
                    raw_data["SAR"].append((obs_date, dap, props.get('VH_VV')))
    except Exception as e:
        print(f"  Warning: Sentinel-1 query failed: {e}")

    # --- C. ERA5-Land Weather ---
    print("Fetching ERA5-Land weather parameters...")
    era5 = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR') \
        .filterBounds(roi) \
        .filterDate(p_date_str, end_date_str) \
        .select(['temperature_2m', 'dewpoint_temperature_2m', 'total_precipitation_sum', 
                 'u_component_of_wind_10m', 'v_component_of_wind_10m'])
        
    def get_weather_stats(image):
        date = image.date().format('YYYY-MM-dd')
        # Use first at centroid (scale 11132 for ~9km grid)
        stats = image.reduceRegion(reducer=ee.Reducer.first(), geometry=centroid, scale=11132, maxPixels=1e9)
        return ee.Feature(None, stats).set('date', date)
        
    try:
        weather_features = ee.FeatureCollection(era5.map(get_weather_stats)).getInfo()['features']
        print(f"  Found {len(weather_features)} weather observation days.")
        for feat in weather_features:
            props = feat['properties']
            obs_date = props.get('date')
            if obs_date and props.get('temperature_2m') is not None:
                dap = (datetime.datetime.strptime(obs_date, "%Y-%m-%d").date() - farm['planting_date']).days
                if dap >= 0:
                    t_c = props['temperature_2m'] - 273.15
                    td_c = props['dewpoint_temperature_2m'] - 273.15
                    
                    # RH formula
                    rh = 100 * np.exp((17.625 * td_c) / (243.04 + td_c)) / np.exp((17.625 * t_c) / (243.04 + t_c))
                    # Wind speed
                    wind_speed = np.sqrt(props['u_component_of_wind_10m']**2 + props['v_component_of_wind_10m']**2)
                    # Precipitation in mm
                    precip_mm = props['total_precipitation_sum'] * 1000
                    
                    raw_data["temp"].append((obs_date, dap, t_c))
                    raw_data["precip"].append((obs_date, dap, precip_mm))
                    raw_data["RH"].append((obs_date, dap, rh))
                    raw_data["wind"].append((obs_date, dap, wind_speed))
    except Exception as e:
        print(f"  Warning: ERA5-Land query failed: {e}")

    # 4. Bin and aggregate observations using 15-day intervals and median calculation
    print("Binning and aggregating data into 15-day median windows...")
    output_binned = {}
    all_dates = []
    
    for feature, obs_list in raw_data.items():
        bin_groups = {}
        for obs_date, dap, val in obs_list:
            if val is None or np.isnan(val):
                continue
            all_dates.append(obs_date)
            
            dap_bin = (dap // 15) * 15
            if dap_bin not in bin_groups:
                bin_groups[dap_bin] = []
            bin_groups[dap_bin].append(val)
            
        binned_vals = []
        for dap_bin, vals in bin_groups.items():
            median_val = float(np.median(vals))
            binned_vals.append({
                "dap_bin": int(dap_bin),
                "observed": median_val
            })
            
        # Sort by dap_bin ascending
        binned_vals.sort(key=lambda x: x["dap_bin"])
        output_binned[feature] = binned_vals

    # Compute key timeline summary items
    current_dap = (datetime.date.today() - farm['planting_date']).days
    last_obs_date = max(all_dates) if all_dates else None
    
    # 5. Build output payload
    output_payload = {
        "farm_id": farm['farm_id'],
        "variety": farm['variety'],
        "planting_date": farm['planting_date_str'],
        "latitude": farm['latitude'],
        "longitude": farm['longitude'],
        "field_area_acres": farm['field_area_acres'],
        "twin_type": "new_farm",
        "current_dap": current_dap,
        "last_observation_date": last_obs_date,
        "NDVI": output_binned.get("NDVI", []),
        "NDRE": output_binned.get("NDRE", []),
        "NDWI": output_binned.get("NDWI", []),
        "EVI": output_binned.get("EVI", []),
        "MSAVI": output_binned.get("MSAVI", []),
        "SAR": output_binned.get("SAR", []),
        "temp": output_binned.get("temp", []),
        "precip": output_binned.get("precip", []),
        "RH": output_binned.get("RH", []),
        "wind": output_binned.get("wind", [])
    }
    
    # Save output to JSON
    output_file_path = farm['output_file']
    print(f"Saving output payload to: {output_file_path}")
    try:
        with open(output_file_path, 'w') as f:
            json.dump(output_payload, f, indent=2)
        print("Success! Live query script finished execution.")
    except Exception as e:
        print(f"Error: Failed to write JSON output: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
