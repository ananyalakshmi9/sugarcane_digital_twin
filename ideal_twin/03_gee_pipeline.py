import ee
import pandas as pd
import numpy as np

def run_gee_pipeline(farm_data_path, coord_path, output_path):
    ee.Initialize(project='harvest-maximizer')
    
    # Load farms
    farms_df = pd.read_csv(farm_data_path)
    
    # Load coordinates
    coords_df = pd.read_excel(coord_path, sheet_name='Coordinates')
    coords_df['Farm_id'] = coords_df['Farm_id'].ffill()
    coords_df = coords_df.dropna(subset=['Lat', 'Long'])
    
    # Build polygons
    polygons = {}
    for farm_id, group in coords_df.groupby('Farm_id'):
        pts = group[['Long', 'Lat']].values.tolist()
        if len(pts) >= 3:
            polygons[int(farm_id)] = ee.Geometry.Polygon([pts])
            
    records = []
    
    # S2 indices function
    def add_indices(image):
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

    for _, row in farms_df.iterrows():
        farm_id = int(row['farm_id'])
        season = row['season']
        p_date = str(row['planting_date']).split(' ')[0]
        h_date = str(row['harvest_date']).split(' ')[0]
        
        if farm_id not in polygons:
            print(f"Skipping farm {farm_id}: No coordinates found.")
            continue
            
        roi = polygons[farm_id]
        
        # Sentinel-2
        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(roi) \
            .filterDate(p_date, h_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) \
            .map(add_indices)
            
        def get_s2_stats(image):
            date = image.date().format('YYYY-MM-dd')
            stats = image.select(['NDVI', 'NDRE', 'NDWI', 'EVI', 'MSAVI']).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=10,
                maxPixels=1e9
            )
            return ee.Feature(None, stats).set('date', date)
            
        try:
            s2_features = ee.FeatureCollection(s2.map(get_s2_stats)).getInfo()['features']
            for feat in s2_features:
                props = feat['properties']
                if props.get('NDVI') is not None:
                    dap = (pd.to_datetime(props['date']) - pd.to_datetime(p_date)).days
                    records.append({
                        'farm_id': farm_id,
                        'season': season,
                        'observation_date': props['date'],
                        'DAP': dap,
                        'NDVI': props.get('NDVI'),
                        'NDRE': props.get('NDRE'),
                        'NDWI': props.get('NDWI'),
                        'EVI': props.get('EVI'),
                        'MSAVI': props.get('MSAVI'),
                        'VH_VV': np.nan,
                        'temperature_2m': np.nan,
                        'total_precipitation_sum': np.nan,
                        'relative_humidity': np.nan,
                        'wind_speed_10m': np.nan
                    })
        except Exception as e:
            print(f"S2 failed for {farm_id}: {e}")

        # ERA5-Land Weather
        era5 = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR') \
            .filterBounds(roi) \
            .filterDate(p_date, h_date) \
            .select(['temperature_2m', 'dewpoint_temperature_2m', 'total_precipitation_sum', 'u_component_of_wind_10m', 'v_component_of_wind_10m'])
            
        def get_weather_stats(image):
            date = image.date().format('YYYY-MM-dd')
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=11132, # ERA5-Land scale
                maxPixels=1e9
            )
            return ee.Feature(None, stats).set('date', date)
            
        try:
            weather_features = ee.FeatureCollection(era5.map(get_weather_stats)).getInfo()['features']
            for feat in weather_features:
                props = feat['properties']
                if props.get('temperature_2m') is not None:
                    dap = (pd.to_datetime(props['date']) - pd.to_datetime(p_date)).days
                    
                    # Compute derived variables
                    t_c = props['temperature_2m'] - 273.15
                    td_c = props['dewpoint_temperature_2m'] - 273.15
                    rh = 100 * np.exp((17.625 * td_c) / (243.04 + td_c)) / np.exp((17.625 * t_c) / (243.04 + t_c))
                    wind_speed = np.sqrt(props['u_component_of_wind_10m']**2 + props['v_component_of_wind_10m']**2)
                    precip_mm = props['total_precipitation_sum'] * 1000
                    
                    records.append({
                        'farm_id': farm_id,
                        'season': season,
                        'observation_date': props['date'],
                        'DAP': dap,
                        'NDVI': np.nan,
                        'NDRE': np.nan,
                        'NDWI': np.nan,
                        'EVI': np.nan,
                        'MSAVI': np.nan,
                        'VH_VV': np.nan,
                        'temperature_2m': t_c,
                        'total_precipitation_sum': precip_mm,
                        'relative_humidity': rh,
                        'wind_speed_10m': wind_speed
                    })
        except Exception as e:
            print(f"Weather failed for {farm_id}: {e}")

    gee_df = pd.DataFrame(records)
    
    gee_df.to_csv(output_path, index=False)
    print(f"Saved {len(gee_df)} actual GEE observations to {output_path}")

if __name__ == "__main__":
    run_gee_pipeline('data/cleaned/farm_data_weighted.csv', 'data/raw/coordinates.xlsx', 'data/gee_outputs/indices_by_dap.csv')
