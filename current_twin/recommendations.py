import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

SYSTEM_INSTRUCTION = """You are an experienced sugarcane agronomist advising farmers in Maharashtra, India.
This is a farm currently mid-season. Based on the satellite-derived deviations so far,
give 3–5 specific actionable interventions the farmer should take RIGHT NOW or in the 
next 14 days. For each output:
- intervention: what to do
- timing: immediate / within 7 days / within 14 days
- expected_outcome: what improvement to expect
- urgency: immediate / within_7_days / monitor
Output as a JSON array only. No explanation text."""

def parse_args():
    parser = argparse.ArgumentParser(description="Call Gemini API to append agronomic recommendations to a farm's gap report.")
    parser.add_argument("gap_report", type=str, help="Path to the farm's gap report JSON.")
    parser.add_argument("--env-file", type=str, default=".env",
                        help="Path to the env file containing the API key.")
    parser.add_argument("--output-file", "-o", type=str, default=None,
                        help="Path to write the merged report. If omitted, overwrites the input gap report file in-place.")
    return parser.parse_args()

def get_ollama_config(env_path):
    """Retrieve Ollama configurations from environment or .env file."""
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv() # Fallback to default .env lookup
        
    url = os.getenv("OLLAMA_API_URL")
    model = os.getenv("OLLAMA_MODEL", "sike_aditya/AgriLlama")
    
    if not url:
        # Auto-detect if running inside Docker or directly on host
        if os.path.exists('/.dockerenv'):
            url = "http://host.docker.internal:11434"
        else:
            url = "http://localhost:11434"
    else:
        # If OLLAMA_API_URL is set (e.g. to host.docker.internal) but we are NOT inside Docker,
        # fallback to localhost so host testing works out-of-the-box.
        if not os.path.exists('/.dockerenv') and "host.docker.internal" in url:
            url = url.replace("host.docker.internal", "localhost")
            
    return url, model

def build_agronomic_prompt(report):
    """Prepare context-rich prompt for the agronomist model."""
    variety = report.get("variety", "Unknown")
    current_dap = report.get("current_dap", 0)
    health_score = report.get("overall_health_score", 0.0)
    
    # Growth stage at current_dap
    current_stage = "Unknown"
    for feat, bins in report.get("deviations", {}).items():
        if bins:
            current_stage = bins[-1].get("growth_stage", "Unknown")
            break
            
    # Calculate available vs expected bins
    available_bins = 0
    for feat, bins in report.get("deviations", {}).items():
        available_bins = max(available_bins, len(bins))
        
    total_duration_days = 540 if variety == "CO_265" else 420
    total_expected_bins = total_duration_days // 15
    
    # Format the top 3 deviations
    top_deviations = report.get("top_urgent_deviations", [])
    deviations_str = ""
    for idx, item in enumerate(top_deviations):
        feat = item.get("feature")
        consec_red = item.get("consecutive_red_bins")
        max_pct = item.get("max_percentage_deviation")
        display_name = item.get("feature_display_name", feat)
        
        # Determine direction of last bin
        direction = "deviation"
        feat_bins = report.get("deviations", {}).get(feat, [])
        if feat_bins:
            last_bin = feat_bins[-1]
            pct_dev = last_bin.get("percentage_deviation")
            if pct_dev is not None:
                direction = "above ideal" if pct_dev > 0 else "below ideal"
                
        deviations_str += f"- Feature: {display_name}\n"
        deviations_str += f"  Max Percentage Deviation: {max_pct:.1f}% ({direction})\n"
        deviations_str += f"  Consecutive RED Bins: {consec_red}\n"
        
    prompt = f"""Sugarcane Farm Digital Twin Anomaly Report:
- Crop Variety: {variety}
- Current Growth Stage: {current_stage}
- Current Days After Planting (DAP): {current_dap}
- Overall Health Score: {health_score}/100
- Data Scope: {available_bins} binned measurements (out of {total_expected_bins} expected bins for full crop lifecycle)

Top Critical Deviations Detected:
{deviations_str if deviations_str else "- None detected."}
"""
    return prompt

def call_ollama_api(url, model, prompt_content, system_instr):
    """Call Ollama's Chat API with JSON output constraint."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instr},
            {"role": "user", "content": prompt_content}
        ],
        "stream": False,
        "options": {
            "temperature": 0.2
        },
        "format": "json"
    }
    # 45-second timeout for local model generation
    response = requests.post(f"{url}/api/chat", json=payload, timeout=45)
    response.raise_for_status()
    res_json = response.json()
    
    prompt_tokens = res_json.get("prompt_eval_count", 0)
    response_tokens = res_json.get("eval_count", 0)
    if prompt_tokens or response_tokens:
        print(f"Token Usage - Prompt: {prompt_tokens}, Response: {response_tokens}, Total: {prompt_tokens + response_tokens}")
        
    content = res_json.get("message", {}).get("content", "")
    return content

def clean_recommendations(data):
    """Robustly clean and extract a standardized list of recommendations from LLM output."""
    raw_list = []
    
    # 1. Extract the list from dictionary if LLM wrapped it
    if isinstance(data, dict):
        list_keys = []
        for k, v in data.items():
            if isinstance(v, list):
                list_keys.append(k)
        
        if list_keys:
            # Prioritize matching keys containing 'intervention' or 'recommendation' or 'action' or 'list'
            priority_keys = [k for k in list_keys if any(x in k.lower() for x in ["interv", "recom", "action", "list", "plan"])]
            chosen_key = priority_keys[0] if priority_keys else list_keys[0]
            raw_list = data[chosen_key]
        else:
            # Check if dict itself represents a single recommendation
            if any(x in data for x in ["intervention", "description", "action"]):
                raw_list = [data]
            else:
                for k, v in data.items():
                    if isinstance(v, dict):
                        raw_list.append(v)
    elif isinstance(data, list):
        raw_list = data
        
    cleaned_list = []
    for item in raw_list:
        if isinstance(item, str):
            cleaned_list.append({
                "intervention": item,
                "timing": "immediate",
                "expected_outcome": "Improvement of crop health.",
                "urgency": "monitor"
            })
            continue
            
        if not isinstance(item, dict):
            continue
            
        intervention = item.get("intervention") or item.get("description") or item.get("action") or item.get("type") or item.get("text") or "AI recommendation"
        timing = item.get("timing") or "immediate"
        expected_outcome = item.get("expected_outcome") or item.get("outcome") or item.get("expected") or item.get("result") or "Improvement of crop health."
        urgency = item.get("urgency") or "monitor"
        
        urg_lower = str(urgency).lower()
        if "high" in urg_lower or "critical" in urg_lower or "immediate" in urg_lower:
            urgency = "immediate"
        elif "medium" in urg_lower or "7" in urg_lower:
            urgency = "within_7_days"
        elif "low" in urg_lower or "monitor" in urg_lower or "14" in urg_lower:
            urgency = "monitor"
            
        cleaned_list.append({
            "intervention": str(intervention).strip(),
            "timing": str(timing).strip(),
            "expected_outcome": str(expected_outcome).strip(),
            "urgency": str(urgency).strip()
        })
        
    return cleaned_list

def main():
    args = parse_args()
    
    # 1. Retrieve Ollama Config
    url, model = get_ollama_config(args.env_file)
    print(f"Configured Ollama URL: {url}")
    print(f"Configured Ollama Model: {model}")
        
    # 2. Load Gap Report
    if not os.path.exists(args.gap_report):
        print(f"Error: Gap report JSON not found at {args.gap_report}")
        sys.exit(1)
        
    with open(args.gap_report, 'r') as f:
        report = json.load(f)
        
    # 3. Build Prompt
    prompt_content = build_agronomic_prompt(report)
    print("\n--- Constructing LLM Prompt ---")
    print(prompt_content)
    print("--------------------------------\n")
    
    # 4. Generate Recommendations via Ollama
    print("Calling Ollama API...")
    recommendations = None
    last_err = None
    
    try:
        content = call_ollama_api(url, model, prompt_content, SYSTEM_INSTRUCTION)
        parsed_json = json.loads(content)
        recommendations = clean_recommendations(parsed_json)
        print(f"Success with local model {model}!")
    except json.JSONDecodeError as je:
        print(f"JSON Parse Error: Ollama returned invalid JSON syntax. Details: {je}")
        last_err = je
    except requests.exceptions.RequestException as re:
        print(f"Ollama API Connection Error: {re}")
        print("\nEnsure Ollama is running on your Mac host:")
        print("1. Download & open Ollama (https://ollama.com)")
        print(f"2. Pull the model: ollama pull {model}")
        last_err = re
    except Exception as e:
        print(f"Unexpected error calling Ollama: {e}")
        last_err = e
            
    if recommendations is None:
        print(f"\n[WARNING] Ollama local LLM generation failed. Last error: {last_err}")
        print("Falling back to offline mock/heuristics to avoid crashing the pipeline...")
        recommendations = [
            {
                "intervention": "AI Agronomist service is temporarily unavailable. Please refer to Expert Rule Alerts for specific field actions.",
                "timing": "immediate",
                "expected_outcome": "Resolution of offline alert.",
                "urgency": "monitor"
            }
        ]
        
    # 5. Merge Recommendations and Save
    report["llm_recommendations"] = recommendations
    
    out_path = args.output_file if args.output_file else args.gap_report
    print(f"Saving updated report with recommendations to: {out_path}")
    try:
        with open(out_path, 'w') as f:
            json.dump(report, f, indent=2)
        print("Success! Recommendations merged successfully.")
    except Exception as e:
        print(f"Error writing to output file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
