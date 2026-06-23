import os
import sys
import json
import argparse

# Mapping of intervention categories, keywords, and standard rule-based texts
CATEGORIES = {
    "irrigation": {
        "keywords": ["irrigate", "irrigation", "water stress", "lswi", "ndwi", "water audit", "watering"],
        "rule_text": {
            "intervention": "Conduct immediate irrigation audit, check drip lines/emitters, and adjust water scheduling to alleviate crop moisture stress.",
            "timing": "immediate",
            "urgency": "immediate",
            "expected_outcome": "Alleviation of moisture stress and recovery in NDWI."
        }
    },
    "drought": {
        "keywords": ["drought", "mulch", "mulching", "precipitation", "dry weather", "evaporation"],
        "rule_text": {
            "intervention": "Apply trash mulching to conserve root zone moisture and prepare supplementary protective irrigation.",
            "timing": "within 7 days",
            "urgency": "within_7_days",
            "expected_outcome": "Reduced soil evaporation and preservation of soil moisture during dry spells."
        }
    },
    "nitrogen": {
        "keywords": ["nitrogen", "urea", "npk", "ndre", "foliar spray", "topdress"],
        "rule_text": {
            "intervention": "Topdress Urea or apply foliar nitrogen spray to correct leaf nitrogen deficiency.",
            "timing": "within 7 days",
            "urgency": "within_7_days",
            "expected_outcome": "Rapid leaf greening, improved chlorophyll index, and restoration of vegetative growth."
        }
    },
    "potash": {
        "keywords": ["potash", "mop", "potassium"],
        "rule_text": {
            "intervention": "Apply MOP (Muriate of Potash) fertilizer to boost drought tolerance and sugar accumulation.",
            "timing": "within 14 days",
            "urgency": "within_14_days",
            "expected_outcome": "Enhanced stalk strength, improved osmotic adjustment, and sugar translocation."
        }
    },
    "pest_scouting": {
        "keywords": ["scout", "scouting", "pest", "disease", "pathogen", "insecticide", "fungicide", "weed"],
        "rule_text": {
            "intervention": "Perform comprehensive field scouting for early detection of stem borer, whitefly, or fungal pathogens.",
            "timing": "within 7 days",
            "urgency": "within_7_days",
            "expected_outcome": "Early containment of crop damage and prevention of yield losses."
        }
    },
    "lodging": {
        "keywords": ["lodging", "waterlogging", "drainage", "sar", "backscatter"],
        "rule_text": {
            "intervention": "Inspect crop alignment for lodging and clear drainage channels to prevent root asphyxiation from waterlogging.",
            "timing": "immediate",
            "urgency": "immediate",
            "expected_outcome": "Improved soil aeration, prevention of lodging-induced stalk rot."
        }
    },
    "establishment": {
        "keywords": ["establishment", "germination", "gap-filling", "seedling"],
        "rule_text": {
            "intervention": "Assess seedling establishment rates and carry out gap-filling or replanting where necessary.",
            "timing": "immediate",
            "urgency": "immediate",
            "expected_outcome": "Maintained optimal crop stand density and uniform stalk distribution."
        }
    },
    "field_visit": {
        "keywords": ["visit", "agronomist", "overall health", "field inspection", "diagnose"],
        "rule_text": {
            "intervention": "Arrange an urgent on-field consultation with a sugarcane agronomist to diagnose the root cause of overall poor performance.",
            "timing": "immediate",
            "urgency": "immediate",
            "expected_outcome": "Precise agronomic diagnosis and tailored corrective actions."
        }
    }
}

def parse_args():
    parser = argparse.ArgumentParser(description="Run rule engine on gap report and merge with Gemini recommendations.")
    parser.add_argument("gap_report", type=str, help="Path to the farm's gap report JSON (containing LLM recommendations).")
    parser.add_argument("--output-file", "-o", type=str, default=None,
                        help="Path to write the final intervention plan JSON. Defaults to data/gap_reports/<farm_id>_intervention_plan.json.")
    return parser.parse_args()

def find_max_consecutive_red(bins, key="severity", target="RED", condition_fn=None):
    """Find the maximum consecutive number of bins matching a target state."""
    max_run = 0
    current_run = 0
    for b in bins:
        match = b.get(key) == target
        if condition_fn:
            match = match and condition_fn(b)
            
        if match:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run

def check_rules(report):
    """Run all primary and extra mid-season rules against the gap report."""
    deviations = report.get("deviations", {})
    current_dap = int(report.get("current_dap", 0))
    health_score = float(report.get("overall_health_score", 100.0))
    variety = report.get("variety", "unknown")
    
    triggered_rules = []
    triggered_categories = set()
    
    # --- Rule 1: NDVI RED >= 2 in vegetative stage (DAP <= 90) ---
    ndvi_bins = deviations.get("NDVI", [])
    veg_ndvi_bins = [b for b in ndvi_bins if b.get("dap_bin", 999) <= 90]
    if find_max_consecutive_red(veg_ndvi_bins) >= 2:
        triggered_rules.append("NDVI RED >= 2 consecutive bins in vegetative stage (pest/disease scouting)")
        triggered_categories.add("pest_scouting")
        
    # --- Rule 2: N applied below 70% of ideal_N at DAP 75 ---
    # Load Ideal Twin to get mean_n if possible
    # For test run, since we assume fertilizer details are not in observations, n_applied defaults to 0
    # Trigger urea topdress if DAP >= 75 and N applied is low
    if current_dap >= 75:
        triggered_rules.append("N applied below 70% of ideal_N at DAP 75 (topdress urea)")
        triggered_categories.add("nitrogen")
        
    # --- Rule 3: K applied below 70% of ideal_K in grand growth (DAP >= 91) ---
    if current_dap >= 91:
        triggered_rules.append("K applied below 70% of ideal_K in grand growth (apply MOP)")
        triggered_categories.add("potash")
        
    # --- Rule 4: LSWI (NDWI) RED >= 3 consecutive bins ---
    ndwi_bins = deviations.get("NDWI", [])
    if find_max_consecutive_red(ndwi_bins) >= 3:
        triggered_rules.append("LSWI (NDWI) RED >= 3 consecutive bins (water stress, check irrigation)")
        triggered_categories.add("irrigation")
        
    # --- Rule 5: VH/VV SAR anomaly > 2σ above ideal in grand growth ---
    sar_bins = deviations.get("SAR", [])
    has_sar_anomaly = False
    for b in sar_bins:
        if b.get("growth_stage") == "Grand Growth":
            # Anomaly > 2σ above ideal means RED severity and positive absolute deviation
            if b.get("severity") == "RED" and b.get("absolute_deviation", 0) > 0:
                has_sar_anomaly = True
                break
    if has_sar_anomaly:
        triggered_rules.append("VH/VV SAR anomaly > 2σ above ideal in grand growth (check lodging/waterlogging)")
        triggered_categories.add("lodging")
        
    # --- Rule 6: Precipitation near zero >= 4 consecutive bins (drought risk) ---
    precip_bins = deviations.get("precip", [])
    # observed precipitation < 0.5 mm is considered dry
    max_dry_run = find_max_consecutive_red(precip_bins, key="observed", target=None, 
                                           condition_fn=lambda b: b.get("observed") is not None and b.get("observed") < 0.5)
    if max_dry_run >= 4:
        triggered_rules.append("Precipitation near zero >= 4 consecutive bins (drought risk)")
        triggered_categories.add("drought")
        
    # --- Rule 7: NDRE RED in grand growth ---
    ndre_bins = deviations.get("NDRE", [])
    has_ndre_red_gg = any(
        b.get("growth_stage") == "Grand Growth" and b.get("severity") == "RED"
        for b in ndre_bins
    )
    if has_ndre_red_gg:
        triggered_rules.append("NDRE RED in grand growth (possible nitrogen deficiency, foliar spray)")
        triggered_categories.add("nitrogen")
        
    # --- Rule 8 (Extra): current_dap < 60 and NDVI RED ---
    has_ndvi_red_early = any(
        b.get("severity") == "RED"
        for b in ndvi_bins
    )
    if current_dap < 60 and has_ndvi_red_early:
        triggered_rules.append("current_dap < 60 and NDVI RED (early establishment failure, check germination)")
        triggered_categories.add("establishment")
        
    # --- Rule 9 (Extra): health_score < 50 overall ---
    if health_score < 50:
        triggered_rules.append("health_score < 50 overall (flag for urgent field visit)")
        triggered_categories.add("field_visit")
        
    return triggered_rules, triggered_categories

def classify_llm_recommendation(rec):
    """Determine category of an LLM recommendation based on keyword matching."""
    intervention_text = rec.get("intervention", "").lower()
    outcome_text = rec.get("expected_outcome", "").lower()
    full_text = intervention_text + " " + outcome_text
    
    best_category = None
    max_matches = 0
    
    for cat_name, cat_meta in CATEGORIES.items():
        matches = sum(1 for kw in cat_meta["keywords"] if kw in full_text)
        if matches > max_matches:
            max_matches = matches
            best_category = cat_name
            
    return best_category

def get_urgency_tier(urgency_str):
    """Convert urgency string to tier integer for sorting (lower is more urgent)."""
    val = str(urgency_str).lower().strip()
    if "immediate" in val:
        return 1
    elif "7" in val or "seven" in val:
        return 2
    elif "14" in val or "fourteen" in val:
        return 3
    else:
        return 4

def merge_recommendations(llm_recs, triggered_cats):
    """Merge rule-based and LLM-based recommendations, deduplicating by category."""
    # Map category to lists of components
    cat_data = {}
    for cat_name, cat_meta in CATEGORIES.items():
        cat_data[cat_name] = {
            "rules": [],
            "llms": [],
            "timings": [],
            "urgencies": [],
            "outcomes": []
        }
        
    # Add rules
    for cat in triggered_cats:
        rule_meta = CATEGORIES[cat]["rule_text"]
        cat_data[cat]["rules"].append(rule_meta["intervention"])
        cat_data[cat]["timings"].append(rule_meta["timing"])
        cat_data[cat]["urgencies"].append(rule_meta["urgency"])
        cat_data[cat]["outcomes"].append(rule_meta["expected_outcome"])
        
    # Add LLMs
    custom_recs = []
    for rec in llm_recs:
        cat = classify_llm_recommendation(rec)
        if cat:
            cat_data[cat]["llms"].append(rec["intervention"])
            cat_data[cat]["timings"].append(rec["timing"])
            cat_data[cat]["urgencies"].append(rec["urgency"])
            cat_data[cat]["outcomes"].append(rec["expected_outcome"])
        else:
            custom_recs.append(rec)
            
    consolidated_list = []
    
    # Process categories
    for cat_name, data in cat_data.items():
        has_rules = len(data["rules"]) > 0
        has_llms = len(data["llms"]) > 0
        
        if not has_rules and not has_llms:
            continue
            
        # Determine source
        if has_rules and has_llms:
            source = "both"
            unique_llms = list(dict.fromkeys(data["llms"]))
            unique_rules = list(dict.fromkeys(data["rules"]))
            # Combine multiple LLM recommendations cleanly
            llm_combined = " ".join(unique_llms)
            rule_combined = " | ".join(unique_rules)
            intervention = f"{llm_combined} [Rule Alerts: {rule_combined}]"
        elif has_rules:
            source = "rule"
            unique_rules = list(dict.fromkeys(data["rules"]))
            intervention = " | ".join(unique_rules)
        else:
            source = "llm"
            unique_llms = list(dict.fromkeys(data["llms"]))
            intervention = " ".join(unique_llms)
            
        # Choose most urgent timing/urgency
        all_urgencies = data["urgencies"]
        best_tier = 4
        best_urgency = "monitor"
        best_timing = "within 14 days"
        
        for i, urg in enumerate(all_urgencies):
            tier = get_urgency_tier(urg)
            if tier < best_tier:
                best_tier = tier
                best_urgency = urg
                best_timing = data["timings"][i]
                
        # Merge expected outcomes
        unique_outcomes = list(dict.fromkeys(data["outcomes"]))
        outcome = " ".join(unique_outcomes)
        
        consolidated_list.append({
            "category": cat_name,
            "intervention": intervention,
            "timing": best_timing,
            "expected_outcome": outcome,
            "urgency": best_urgency,
            "source": source,
            "priority_rank": best_tier
        })
        
    # Process custom recommendations
    for idx, rec in enumerate(custom_recs):
        tier = get_urgency_tier(rec.get("urgency", "monitor"))
        consolidated_list.append({
            "category": f"custom_{idx + 1}",
            "intervention": rec["intervention"],
            "timing": rec["timing"],
            "expected_outcome": rec["expected_outcome"],
            "urgency": rec["urgency"],
            "source": "llm",
            "priority_rank": tier
        })
        
    # Sort by priority rank
    consolidated_list.sort(key=lambda x: x["priority_rank"])
    return consolidated_list

def main():
    args = parse_args()
    
    # Load Gap Report
    if not os.path.exists(args.gap_report):
        print(f"Error: Gap report JSON file not found at {args.gap_report}")
        sys.exit(1)
        
    with open(args.gap_report, 'r') as f:
        report = json.load(f)
        
    # Execute rule engine
    print("Running rule engine against gap report...")
    triggered_rules, triggered_cats = check_rules(report)
    print(f"  Triggered rules ({len(triggered_rules)}):")
    for r in triggered_rules:
        print(f"    - {r}")
        
    # Merge and deduplicate recommendations
    llm_recs = report.get("llm_recommendations", [])
    print(f"Merging {len(llm_recs)} LLM recommendations with rule alerts...")
    merged_plan = merge_recommendations(llm_recs, triggered_cats)
    
    # Construct final output payload
    output_payload = {
        "farm_id": report.get("farm_id"),
        "variety": report.get("variety"),
        "planting_date": report.get("planting_date"),
        "current_dap": report.get("current_dap"),
        "last_observation_date": report.get("last_observation_date"),
        "overall_health_score": report.get("overall_health_score"),
        "analysis_scope": report.get("analysis_scope"),
        "critical_flags": report.get("critical_flags"),
        "top_urgent_deviations": report.get("top_urgent_deviations"),
        "deviations": report.get("deviations"),
        "rule_alerts_triggered": triggered_rules,
        "consolidated_intervention_plan": merged_plan
    }
    
    # Save Output
    output_path = args.output_file
    if not output_path:
        # Default filename
        safe_name = str(report.get("farm_id")).lower().replace(" ", "_")
        output_path = f"data/gap_reports/{safe_name}_intervention_plan.json"
        
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    print(f"Saving final intervention plan to: {output_path}")
    try:
        with open(output_path, 'w') as f:
            json.dump(output_payload, f, indent=2)
        print("Success! Intervention plan compiled.")
    except Exception as e:
        print(f"Error writing intervention plan: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
