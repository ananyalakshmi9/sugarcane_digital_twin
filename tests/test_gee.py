import os
import ee
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()
ee.Initialize(project=os.getenv("GEE_PROJECT_ID", "harvest-maximizer"))
roi = ee.Geometry.Point([74.13846, 20.78991]).buffer(100)
p_date = '2023-01-01'
h_date = '2023-01-10'
era5 = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').filterBounds(roi).filterDate(p_date, h_date).select(['temperature_2m'])
def get_weather_stats(image):
    date = image.date().format('YYYY-MM-dd')
    stats = image.reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=11132)
    return ee.Feature(None, stats).set('date', date)
feats = ee.FeatureCollection(era5.map(get_weather_stats)).getInfo()['features']
print(feats)
