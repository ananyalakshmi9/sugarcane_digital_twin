# Sugarcane Crop Digital Twin Platform

An advanced agricultural decision-support platform designed to monitor sugarcane crop health, detect anomalies, evaluate daily growth gaps, and compile consolidated intervention checklists. Powered by **Google Earth Engine (GEE)**, **ERA5-Land daily weather aggregates**, and **mathematical regression curves**.

---

## 🌟 Key Platform Features

### 1. Database Separation & Curve Protection
*   **Ideal Reference Database** (`data/raw/Satellite_twin_data.xlsx`): Strictly contains data from high-yielding reference farms used to generate optimal growth curve baselines.
*   **Regular Farmers Database** (`data/raw/Regular_farmers_data.xlsx`): Stores farm profiles registered through the UI or terminal runner.
*   **Quality Gate Isolation**: The cleaning pipeline (`01_data_cleaner.py` and `02_quality_gate.py`) automatically tags records (`is_ideal = 1` or `0`) and excludes regular farmers from contributing to the ideal curves, protecting baseline models from contamination.

### 2. Automated Baseline Recalculation
*   Recalculation is triggered automatically in the background whenever a new farm is registered. It cleans coordinates, computes standard deviations, recalculates smoothed variety curves, and regenerates visual plots without causing UI lag.

### 3. Current Twin Extractor & Autocomplete
*   **Autocomplete Autofill**: Entering/typing a Farm ID in the current twin panel queries the autocomplete API (`/api/farm/<farm_id>`), automatically resolving and pre-populating its centroid coordinates, planting date, acreage, and sugarcane variety.
*   **Live Extractor**: Extracts Sentinel-1 (VV/VH backscatter), Sentinel-2 (NDVI, NDRE, NDWI, EVI, MSAVI), and ERA5-Land parameters for the farm's active growing season.

### 4. Anomaly Detection & AI Advisory
*   **Daily Gap Alignment**: Aligns the crop's live indexes against the baseline trajectory to flag vigor, moisture, or weather alerts.
*   **Hybrid Recommendations**: Combines expert agronomic rule alerts (waterlogging, nitrogen deficiency, irrigation stress) with a Gemini API AI agronomist layer (featuring an offline mock fallback to ensure the pipeline never crashes).

---

## ⚙️ Setup & Installation

1.  **Dependencies**:
    Ensure you have Python installed, then install required modules:
    ```bash
    pip install pandas numpy openpyxl scipy requests python-dotenv flask
    ```

2.  **Environment Variables**:
    Create a `.env` file at the root of the workspace to configure Google Earth Engine and the Gemini API:
    ```env
    GEE_PROJECT_ID=your-google-earth-engine-project-id
    GEMINI_API_KEY=your-gemini-api-key
    ```

---

## 🚀 How to Run

### Option A: Web User Interface (Flask App)

1.  Start the Flask server on port `5001`:
    ```bash
    python app.py
    ```
2.  Open your browser and navigate to:
    ```text
    http://127.0.0.1:5001
    ```
3.  **Authentication**: Log in using `admin` / `admin`.
4.  **UI Features**:
    *   **Dashboard**: Monitor platform status, farm health distribution, and top-risk fields.
    *   **Ideal Twin**: View baseline curves and register raw records (supports adding new custom varieties using combo-box fields).
    *   **Current Twin**: Extract GEE live indexes (supports coordinates autocomplete).
    *   **Gap Analysis & Conclusion**: Run comparison scans, check health heatmaps, and download consolidated agronomist recommendations.

---

### Option B: Terminal Runner (`run_pipeline.py`)

For command-line operators, you can run all calculations directly in your terminal:

*   **Mode 1: Recalculate Ideal Twin Curves**
    Runs the cleaner, quality gate, feature builder, twin curves builder, and plots generator in sequence:
    ```bash
    python run_pipeline.py --baseline
    ```

*   **Mode 2: Run Live Farm Gap Analysis**
    Pulls live GEE indexes, aligns gaps, evaluates rule triggers, and prints the prioritized advisory plan:
    ```bash
    python run_pipeline.py --analyze \
      --farm-id "Farm_Test_999" \
      --lat 20.78991 \
      --lon 74.13846 \
      --area 3.5 \
      --variety "8005" \
      --planting-date "01-01-2025"
    ```
