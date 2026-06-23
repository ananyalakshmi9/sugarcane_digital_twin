import os
import sys
import json
import argparse
from dotenv import load_dotenv
from google import genai
from google.genai import types

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

def get_api_key(env_path):
    """Retrieve Gemini API Key from environment or .env file."""
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv() # Fallback to default .env lookup
        
    # Read GEMINI_API_KEY first, fallback to ANTHROPIC_API_KEY as requested
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    return api_key

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

def call_gemini_api(api_key, prompt_content, system_instr, model_name='gemini-2.5-flash'):
    """Initialize client and call the Gemini API."""
    client = genai.Client(api_key=api_key)
    
    response = client.models.generate_content(
        model=model_name,
        contents=prompt_content,
        config=types.GenerateContentConfig(
            system_instruction=system_instr,
            response_mime_type="application/json",
            temperature=0.2
        )
    )
    return response

def main():
    args = parse_args()
    
    # 1. Retrieve API key
    api_key = get_api_key(args.env_file)
    if not api_key:
        print("No API key")
        sys.exit(1)
        
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
    
    # 4. Generate Recommendations via Gemini
    print("Calling Gemini API...")
    models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-2.5-pro', 'gemini-1.5-pro']
    recommendations = None
    last_err = None
    
    for model_name in models_to_try:
        try:
            print(f"Trying model: {model_name}...")
            response = call_gemini_api(api_key, prompt_content, SYSTEM_INSTRUCTION, model_name=model_name)
            
            # Log token usage metadata
            usage = response.usage_metadata
            if usage:
                print(f"Token Usage - Prompt: {usage.prompt_token_count}, "
                      f"Response: {usage.candidates_token_count}, "
                      f"Total: {usage.total_token_count}")
            
            # Parse JSON
            recommendations = json.loads(response.text)
            print(f"Success with model: {model_name}!")
            break
            
        except json.JSONDecodeError as je:
            print(f"JSON Parse Error with model {model_name}: Gemini returned invalid JSON syntax. Retrying with stricter instructions. Details: {je}")
            
            # Retry with stricter system instructions
            stricter_instruction = (
                SYSTEM_INSTRUCTION + 
                "\nCRITICAL: Return ONLY a valid JSON array of objects. "
                "Do not include markdown tags (e.g. ```json). Do not add any leading or trailing remarks."
            )
            try:
                response = call_gemini_api(api_key, prompt_content, stricter_instruction, model_name=model_name)
                
                usage = response.usage_metadata
                if usage:
                    print(f"Token Usage (Retry) - Prompt: {usage.prompt_token_count}, "
                          f"Response: {usage.candidates_token_count}, "
                          f"Total: {usage.total_token_count}")
                          
                recommendations = json.loads(response.text)
                print("Successfully parsed JSON on retry.")
                break
            except Exception as retry_err:
                print(f"API Retry failed for {model_name}: {retry_err}")
                last_err = retry_err
                
        except Exception as e:
            print(f"API Call failed for {model_name}: {e}")
            last_err = e
            
    if recommendations is None:
        print(f"\n[WARNING] All Gemini API attempts failed. Last error: {last_err}")
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
