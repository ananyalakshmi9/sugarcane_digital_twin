import os
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import transforms

# Set modern plotting defaults
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
plt.rcParams['axes.edgecolor'] = '#CCCCCC'
plt.rcParams['axes.linewidth'] = 0.8
plt.rcParams['xtick.color'] = '#555555'
plt.rcParams['ytick.color'] = '#555555'
plt.rcParams['grid.color'] = '#EAEAEA'
plt.rcParams['grid.linewidth'] = 0.6

# Directory configurations
INPUT_DIR = 'data/ideal_twin'
OUTPUT_DIR = 'data/plots'
INDIVIDUAL_DIR = os.path.join(OUTPUT_DIR, 'individual')
COMPARISON_DIR = os.path.join(OUTPUT_DIR, 'comparison')
DASHBOARD_DIR = os.path.join(OUTPUT_DIR, 'dashboards')

# Metadata and styling parameters for indices
INDEX_META = {
    "NDVI": {
        "title": "Normalized Difference Vegetation Index (NDVI)",
        "ylabel": "NDVI Value",
        "color": "#10B981", # Emerald
        "type": "veg"
    },
    "NDRE": {
        "title": "Normalized Difference Red Edge (NDRE)",
        "ylabel": "NDRE Value",
        "color": "#059669", # Deep Green
        "type": "veg"
    },
    "NDWI": {
        "title": "Normalized Difference Water Index (NDWI)",
        "ylabel": "NDWI Value",
        "color": "#06B6D4", # Cyan
        "type": "moisture"
    },
    "EVI": {
        "title": "Enhanced Vegetation Index (EVI)",
        "ylabel": "EVI Value",
        "color": "#047857", # Forest Green
        "type": "veg"
    },
    "MSAVI": {
        "title": "Modified Soil Adjusted Vegetation Index (MSAVI)",
        "ylabel": "MSAVI Value",
        "color": "#84CC16", # Lime Green
        "type": "veg"
    },
    "VH_VV": {
        "title": "SAR VH/VV Backscatter Ratio",
        "ylabel": "Ratio (dB)",
        "color": "#8B5CF6", # Purple
        "type": "radar"
    },
    "temperature_2m": {
        "title": "2m Air Temperature",
        "ylabel": "Temperature (°C)",
        "color": "#F97316", # Orange
        "type": "weather"
    },
    "total_precipitation_sum": {
        "title": "Daily Precipitation Sum",
        "ylabel": "Precipitation (mm)",
        "color": "#2563EB", # Blue
        "type": "weather"
    },
    "relative_humidity": {
        "title": "Relative Humidity",
        "ylabel": "Humidity (%)",
        "color": "#3B82F6", # Sky Blue
        "type": "weather"
    },
    "wind_speed_10m": {
        "title": "10m Wind Speed",
        "ylabel": "Wind Speed (m/s)",
        "color": "#6B7280", # Cool Grey
        "type": "weather"
    }
}

# Pastel colors for growth stages background shading
STAGE_COLORS = {
    "germination": "#FDF6E2",   # Soft Warm Cream
    "tillering": "#F4F9F1",     # Soft Mint
    "grand_growth": "#E8F5E9",  # Soft Green
    "maturation": "#FFF3E0",    # Soft Amber
    "ripening": "#EFEBE9"       # Soft Taupe/Grey
}

VARIETY_META = {
    "CO_265": {"label": "CO_265 (Adsali)", "color": "#EF4444"},   # Coral Red
    "CO_86032": {"label": "CO_86032 (Suru)", "color": "#10B981"}, # Emerald
    "8005": {"label": "8005 (Ref Only)", "color": "#3B82F6"}      # Sky Blue
}

def clean_data(daps, values):
    """Filter out None values to prevent plotting breaks."""
    valid_mask = [v is not None for v in values]
    dap_arr = np.array(daps)[valid_mask]
    val_arr = np.array(values)[valid_mask].astype(float)
    return dap_arr, val_arr

def draw_growth_stages(ax, growth_stages, max_dap=None):
    """Draw vertical background spans for the crop growth stages."""
    sorted_stages = sorted(growth_stages.items(), key=lambda x: x[1][0])
    for stage_name, bounds in sorted_stages:
        start, end = bounds
        color = STAGE_COLORS.get(stage_name, "#F0F0F0")
        
        # Shade the region
        ax.axvspan(start, end, color=color, alpha=0.45, zorder=0)
        
        # Place label text at the top using a blended transform (x in data coords, y in axes fraction)
        x_mid = (start + end) / 2
        ax.text(
            x_mid, 0.96,
            stage_name.replace('_', ' ').title(),
            transform=ax.get_xaxis_transform(),
            ha='center', va='top',
            fontsize=7, fontweight='bold',
            color='#4B5563',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#FFFFFFD8', edgecolor='none', alpha=0.85)
        )
    
    if max_dap:
        ax.set_xlim(0, max_dap)
    else:
        ax.set_xlim(0, 360)

def style_axes(ax, index_name, title=None, ylabel=None):
    """Apply unified high-quality styling to the subplot."""
    ax.grid(True, linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#DDDDDD')
    ax.spines['bottom'].set_color('#DDDDDD')
    
    if title:
        ax.set_title(title, fontsize=10, fontweight='bold', color='#1F2937', pad=12)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color='#4B5563')
    ax.set_xlabel("Days After Planting (DAP)", fontsize=9, color='#4B5563')
    
    # Enforce positive limits where negative values are physically impossible
    if index_name in ["NDVI", "NDRE", "EVI", "MSAVI", "total_precipitation_sum", "wind_speed_10m", "relative_humidity"]:
        ax.set_ylim(bottom=0.0)
    elif index_name == "relative_humidity":
        ax.set_ylim(0.0, 105.0)

def load_all_twins():
    """Load all ideal twin files in data/ideal_twin/."""
    twins = {}
    for filename in os.listdir(INPUT_DIR):
        if filename.startswith('ideal_twin_') and filename.endswith('.json'):
            variety = filename.replace('ideal_twin_', '').replace('.json', '')
            filepath = os.path.join(INPUT_DIR, filename)
            with open(filepath, 'r') as f:
                twins[variety] = json.load(f)
    return twins

def plot_individual_curves(twins):
    """Generate individual index plots for each variety."""
    print("Generating individual index curves...")
    for variety, data in twins.items():
        growth_stages = data.get('growth_stages', {})
        curves = data.get('curves', {})
        
        # Determine crop duration
        max_dap = 540 if variety == 'CO_265' else 420
        
        # Generate directory for this variety
        var_dir = os.path.join(INDIVIDUAL_DIR, variety)
        os.makedirs(var_dir, exist_ok=True)
        
        for idx_name, idx_meta in INDEX_META.items():
            if idx_name not in curves:
                continue
            
            curve = curves[idx_name]
            daps = curve['dap']
            mean_vals = curve['mean']
            
            dap_clean, mean_clean = clean_data(daps, mean_vals)
            if len(dap_clean) == 0:
                continue
            
            fig, ax = plt.subplots(figsize=(8.5, 5), dpi=150)
            
            # Plot standard deviation bounds if available
            s1u = curve.get('sigma_1_upper')
            s1l = curve.get('sigma_1_lower')
            s2u = curve.get('sigma_2_upper')
            s2l = curve.get('sigma_2_lower')
            
            has_sigmas = s1u and any(s is not None for s in s1u)
            
            if has_sigmas:
                # Clean sigmas to prevent breaks
                valid_sig1 = [s1u[i] is not None and s1l[i] is not None for i in range(len(daps))]
                valid_sig2 = [s2u[i] is not None and s2l[i] is not None for i in range(len(daps))]
                
                dap_sig1 = np.array(daps)[valid_sig1]
                s1u_clean = np.array(s1u)[valid_sig1].astype(float)
                s1l_clean = np.array(s1l)[valid_sig1].astype(float)
                
                dap_sig2 = np.array(daps)[valid_sig2]
                s2u_clean = np.array(s2u)[valid_sig2].astype(float)
                s2l_clean = np.array(s2l)[valid_sig2].astype(float)
                
                # Plot 2-sigma band (outer, lighter)
                ax.fill_between(
                    dap_sig2, s2l_clean, s2u_clean,
                    color=idx_meta['color'], alpha=0.1,
                    label='±2σ Range (95% CI)', zorder=2
                )
                # Plot 1-sigma band (inner, darker)
                ax.fill_between(
                    dap_sig1, s1l_clean, s1u_clean,
                    color=idx_meta['color'], alpha=0.22,
                    label='±1σ Range (68% CI)', zorder=3
                )
            
            # Plot solid mean line
            ax.plot(
                dap_clean, mean_clean,
                color=idx_meta['color'], linewidth=2.5,
                label='Ideal Twin (Smoothed Mean)', zorder=4
            )
            
            # Shade growth stages
            draw_growth_stages(ax, growth_stages, max_dap=max_dap)
            
            # Apply styling
            title_text = f"{idx_meta['title']} — {variety}"
            if data.get('reference_only', False):
                title_text += " (Reference Only)"
            style_axes(ax, idx_name, title=title_text, ylabel=idx_meta['ylabel'])
            
            # Add Legend
            ax.legend(loc='upper right', frameon=True, facecolor='#FFFFFFD8', edgecolor='none', fontsize=8.5)
            
            # Tight Layout and Save
            plt.tight_layout()
            out_path = os.path.join(var_dir, f"{idx_name}.png")
            plt.savefig(out_path, bbox_inches='tight')
            plt.close()
    print("Individual curves generated successfully.")

def plot_comparison_curves(twins):
    """Plot variety comparison curves overlaying means for each index."""
    print("Generating variety comparison curves...")
    os.makedirs(COMPARISON_DIR, exist_ok=True)
    
    # We can pull growth stages from any variety, as they are standardized
    sample_variety = list(twins.keys())[0]
    growth_stages = twins[sample_variety].get('growth_stages', {})
    
    for idx_name, idx_meta in INDEX_META.items():
        fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
        
        max_seen_dap = 360
        for variety, data in twins.items():
            curves = data.get('curves', {})
            if idx_name not in curves:
                continue
                
            curve = curves[idx_name]
            daps = curve['dap']
            mean_vals = curve['mean']
            
            dap_clean, mean_clean = clean_data(daps, mean_vals)
            if len(dap_clean) == 0:
                continue
                
            max_seen_dap = max(max_seen_dap, dap_clean.max())
            
            var_style = VARIETY_META.get(variety, {"label": variety, "color": "#000000"})
            
            # Plot mean line for this variety
            ax.plot(
                dap_clean, mean_clean,
                color=var_style['color'], linewidth=2.5,
                label=var_style['label'], zorder=4
            )
            
        # Shade growth stages
        draw_growth_stages(ax, growth_stages, max_dap=max_seen_dap)
        
        # Style axes
        style_axes(
            ax, idx_name,
            title=f"Variety Comparison: {idx_meta['title']}",
            ylabel=idx_meta['ylabel']
        )
        
        # Legend
        ax.legend(loc='upper right', frameon=True, facecolor='#FFFFFFD8', edgecolor='none', fontsize=9)
        
        # Save
        plt.tight_layout()
        out_path = os.path.join(COMPARISON_DIR, f"compare_{idx_name}.png")
        plt.savefig(out_path, bbox_inches='tight')
        plt.close()
        
    print("Comparison curves generated successfully.")

def plot_dashboards(twins):
    """Generate a single unified 10-panel dashboard image for each variety."""
    print("Generating variety dashboards...")
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    
    for variety, data in twins.items():
        growth_stages = data.get('growth_stages', {})
        curves = data.get('curves', {})
        
        # Determine crop duration
        max_dap = 540 if variety == 'CO_265' else 420
        
        # Setup 5x2 grid
        fig, axes = plt.subplots(nrows=5, ncols=2, figsize=(15, 20), dpi=120)
        axes = axes.flatten()
        
        # Set main figure title
        ref_suffix = " (Reference Only)" if data.get('reference_only', False) else ""
        metadata = data.get('agronomic_metadata', {})
        subtitle = (f"Yield/Acre: {metadata.get('mean_yield_per_acre', 0.0):.1f} tons | "
                    f"NPK: {metadata.get('mean_n_kg_per_acre', 0.0):.1f}-{metadata.get('mean_p_kg_per_acre', 0.0):.1f}-{metadata.get('mean_k_kg_per_acre', 0.0):.1f} kg/acre | "
                    f"Irrigation: {metadata.get('dominant_irrigation', 'N/A').title()}")
        
        fig.suptitle(
            f"Digital Twin Curves Dashboard: Variety {variety}{ref_suffix}\n"
            f"Source: {data.get('n_farms', 0)} Farms, {data.get('n_farm_seasons', 0)} Farm-Seasons | {subtitle}",
            fontsize=16, fontweight='bold', color='#1F2937', y=0.97
        )
        
        for i, (idx_name, idx_meta) in enumerate(INDEX_META.items()):
            ax = axes[i]
            if idx_name not in curves:
                ax.axis('off')
                continue
                
            curve = curves[idx_name]
            daps = curve['dap']
            mean_vals = curve['mean']
            
            dap_clean, mean_clean = clean_data(daps, mean_vals)
            if len(dap_clean) == 0:
                ax.axis('off')
                continue
                
            # Plot standard deviation bounds if available
            s1u = curve.get('sigma_1_upper')
            s1l = curve.get('sigma_1_lower')
            s2u = curve.get('sigma_2_upper')
            s2l = curve.get('sigma_2_lower')
            
            has_sigmas = s1u and any(s is not None for s in s1u)
            
            if has_sigmas:
                valid_sig1 = [s1u[i] is not None and s1l[i] is not None for i in range(len(daps))]
                valid_sig2 = [s2u[i] is not None and s2l[i] is not None for i in range(len(daps))]
                
                dap_sig1 = np.array(daps)[valid_sig1]
                s1u_clean = np.array(s1u)[valid_sig1].astype(float)
                s1l_clean = np.array(s1l)[valid_sig1].astype(float)
                
                dap_sig2 = np.array(daps)[valid_sig2]
                s2u_clean = np.array(s2u)[valid_sig2].astype(float)
                s2l_clean = np.array(s2l)[valid_sig2].astype(float)
                
                ax.fill_between(dap_sig2, s2l_clean, s2u_clean, color=idx_meta['color'], alpha=0.08, zorder=2)
                ax.fill_between(dap_sig1, s1l_clean, s1u_clean, color=idx_meta['color'], alpha=0.18, zorder=3)
                
            # Plot mean line
            ax.plot(dap_clean, mean_clean, color=idx_meta['color'], linewidth=2.0, zorder=4)
            
            # Shade growth stages
            draw_growth_stages(ax, growth_stages, max_dap=max_dap)
            
            # Apply styling
            style_axes(ax, idx_name, title=idx_meta['title'], ylabel=idx_meta['ylabel'])
            
        # Adjust layout and save
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        out_path = os.path.join(DASHBOARD_DIR, f"dashboard_{variety}.png")
        plt.savefig(out_path, bbox_inches='tight')
        plt.close()
        
    print("Dashboards generated successfully.")

def main():
    print("Starting Digital Twin Visualization Pipeline...")
    
    # Ensure input directory exists
    if not os.path.exists(INPUT_DIR):
        print(f"Error: Input directory {INPUT_DIR} does not exist. Run the ideal twin builder script first.")
        return
        
    # Ensure output directories exist
    os.makedirs(INDIVIDUAL_DIR, exist_ok=True)
    os.makedirs(COMPARISON_DIR, exist_ok=True)
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    
    # Load JSON files
    twins = load_all_twins()
    if not twins:
        print(f"Error: No digital twin JSON files found in {INPUT_DIR}.")
        return
        
    print(f"Loaded digital twin datasets for varieties: {list(twins.keys())}")
    
    # Run plotting functions
    plot_individual_curves(twins)
    plot_comparison_curves(twins)
    plot_dashboards(twins)
    
    print("\nVisualization Pipeline Completed Successfully!")
    print(f"All plots have been saved to: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
