import json
import numpy as np

for variety in ['CO_265', 'CO_86032', '8005']:
    path = f'data/ideal_twin/ideal_twin_{variety}.json'
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            print(f"--- Variety: {variety} ---")
            ndvi_mean = np.array(data['curves']['NDVI']['mean'])
            dap = np.array(data['curves']['NDVI']['dap'])
            
            # Find peak
            valid_idx = [i for i, x in enumerate(ndvi_mean) if x is not None]
            if not valid_idx:
                continue
                
            peak_val = max([ndvi_mean[i] for i in valid_idx])
            peak_dap = dap[valid_idx[np.argmax([ndvi_mean[i] for i in valid_idx])]]
            
            print(f"NDVI Peak: {peak_val:.3f} at DAP {peak_dap}")
            print(f"Growth Stage at Peak: ", end="")
            for stage, bounds in data['growth_stages'].items():
                if bounds[0] <= peak_dap <= bounds[1]:
                    print(stage)
                    
            print(f"Weather samples:")
            temp = data['curves']['temperature_2m']['mean']
            valid_t = [t for t in temp if t is not None]
            if valid_t:
                print(f"  Avg Temp: {np.mean(valid_t):.1f} C, Min: {np.min(valid_t):.1f} C, Max: {np.max(valid_t):.1f} C")
                
            precip = data['curves']['total_precipitation_sum']['mean']
            valid_p = [p for p in precip if p is not None]
            if valid_p:
                print(f"  Avg Daily Precip: {np.mean(valid_p):.2f} mm")

    except Exception as e:
        print(f"Failed {variety}: {e}")
