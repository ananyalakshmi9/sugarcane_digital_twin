# Deployment & Internal Testing Guide

This guide details how to set up, authenticate, and run the Sugarcane Digital Twin platform on another developer's or tester's machine.

---

## Method A: Running with Docker (Recommended)

Running with Docker ensures that all dependencies (like C extensions and packages) are isolated and configured identically.

### 1. Transfer the Project Files
Zip and copy the project folder to the target machine (excluding `__pycache__` and local database files if desired, though keeping `data/app.db` lets them test immediately without migrations).

### 2. Configure Credentials (`.env`)
On the target machine, create a `.env` file at the root of the project:
```env
GEE_PROJECT_ID=your-gcp-gee-project-id
GEMINI_API_KEY=your-gemini-api-key
```

### 3. Handle Google Earth Engine (GEE) Authentication
Google Earth Engine requires a valid GCP credential to authenticate calls:

#### Option 1: Mounting Host Credentials (Easiest for local testers)
If the tester has already run `gcloud auth application-default login` or authenticated GEE on their host machine, you can mount their host credentials directory directly into the Docker container.
*   **Linux/macOS Host**:
    ```bash
    docker run -d \
      -p 5001:5001 \
      --env-file .env \
      -v ~/.config/gcloud:/root/.config/gcloud \
      sugarcane-digital-twin:latest
    ```
*   **Windows Host (PowerShell)**:
    ```powershell
    docker run -d `
      -p 5001:5001 `
      --env-file .env `
      -v $env:APPDATA\gcloud:/root/.config/gcloud `
      sugarcane-digital-twin:latest
    ```

#### Option 2: Using a GCP Service Account Key (Best for standalone containers)
If they don't have local credentials, you can use a GCP Service Account:
1. Create a service account in your GCP Console with the **Earth Engine Resource Viewer / Creator** roles.
2. Download the service account JSON key file (e.g. `service_key.json`) and place it in the project root.
3. Start the container with the environment variable pointing to the key:
   ```bash
   docker run -d \
     -p 5001:5001 \
     --env-file .env \
     -e GOOGLE_APPLICATION_CREDENTIALS=/app/service_key.json \
     sugarcane-digital-twin:latest
   ```

---

## Method B: Running Locally (Without Docker)

If the target machine does not have Docker installed, follow these steps to run the application natively:

### 1. Install System and Python Prerequisites
Ensure Python 3.10+ is installed on the machine.
```bash
# Clone or extract project files, navigate to directory, then install requirements
pip install -r requirements.txt
```

### 2. Authenticate Google Earth Engine
Instruct the tester to run the GEE authorization command in their terminal:
```bash
earthengine authenticate
```
*This opens a browser window to grant access and saves the credential to their local config folder (`~/.config/gcloud`).*

### 3. Initialize/Migrate the Database (If Needed)
If `data/app.db` was not copied over, run the migration script to parse the default Excel sheets and instantiate the SQLite database:
```bash
python db_migration.py
```

### 4. Start the Application
```bash
python app.py
```
Navigate to `http://127.0.0.1:5001` in the browser and log in using credentials `admin` / `admin`.

---

## Method C: Sharing Pre-Built Images Directly

If the tester doesn't want to build the Docker image locally, you can compile and export it as a standalone archive file:

1. **On your machine** (build and export the image):
   ```bash
   docker build -t sugarcane-digital-twin:latest .
   docker save -o sugarcane_twin_image.tar sugarcane-digital-twin:latest
   ```
2. **Transfer** `sugarcane_twin_image.tar` to the target machine (via USB, Shared Drive, Slack, etc.).
3. **On the tester's machine** (load and run the image):
   ```bash
   docker load -i sugarcane_twin_image.tar
   # Run using the commands in Method A
   ```
