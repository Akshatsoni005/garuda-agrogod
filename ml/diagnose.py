"""
Garuda AgroGod - Crop Disease & VRT Prescription Engine
Ponytail: Lightweight rule & feature-based crop health evaluator.
Can be upgraded to YOLOv8-nano / PlantVillage weights with zero pipeline changes.
"""

from typing import Dict, Any, List

# Standard plant pathology diagnostic map (matches Indian agricultural diseases)
CROP_DISEASE_DB = {
    "late_blight": {"crop": "Potato/Tomato", "treatment": "Mancozeb 75% WP", "dosage_ml_per_ha": 250},
    "yellow_rust": {"crop": "Wheat", "treatment": "Propiconazole 25% EC", "dosage_ml_per_ha": 200},
    "blast": {"crop": "Rice/Paddy", "treatment": "Tricyclazole 75% WP", "dosage_ml_per_ha": 300},
    "bollworm": {"crop": "Cotton", "treatment": "Spinosad 45% SC", "dosage_ml_per_ha": 180},
    "healthy": {"crop": "General", "treatment": "None", "dosage_ml_per_ha": 0}
}

def calculate_ndvi(nir_band: float, red_band: float) -> float:
    """Calculate Normalized Difference Vegetation Index (NDVI).
    Values range from -1.0 to 1.0. Healthy crops typically score > 0.45.
    """
    denominator = nir_band + red_band
    if denominator == 0:
        return 0.0
    return round((nir_band - red_band) / denominator, 3)

def evaluate_crop_health(ndvi_score: float, detected_symptom: str = "healthy", field_area_ha: float = 2.5) -> Dict[str, Any]:
    """Generates a precision Variable Rate Technology (VRT) prescription based on NDVI and detected pathology.
    Computes chemical savings compared to traditional blanket broadcast spraying.
    """
    disease_info = CROP_DISEASE_DB.get(detected_symptom.lower(), CROP_DISEASE_DB["healthy"])
    
    # Blanket spraying treats 100% of the field regardless of health
    blanket_volume_liters = (disease_info["dosage_ml_per_ha"] * field_area_ha) / 1000.0
    
    if ndvi_score < 0.35 or detected_symptom.lower() != "healthy":
        # Targeted VRT spraying: only spray stressed zones (estimated 30% of field area)
        affected_fraction = 0.30 if ndvi_score < 0.35 else 0.15
        vrt_volume_liters = round(blanket_volume_liters * affected_fraction, 2)
        action = "DISPATCH_VRT_SPRAY"
        status = "STRESS_DETECTED"
    else:
        vrt_volume_liters = 0.0
        affected_fraction = 0.0
        action = "BYPASS_HEALTHY"
        status = "OPTIMAL_HEALTH"
        
    chemical_saved_pct = round((1.0 - (vrt_volume_liters / blanket_volume_liters if blanket_volume_liters > 0 else 0)) * 100, 1)

    return {
        "status": status,
        "ndvi": ndvi_score,
        "detected_pathology": detected_symptom,
        "recommended_treatment": disease_info["treatment"],
        "recommended_action": action,
        "affected_area_ha": round(field_area_ha * affected_fraction, 2),
        "vrt_spray_volume_liters": vrt_volume_liters,
        "traditional_blanket_liters": round(blanket_volume_liters, 2),
        "chemical_saved_pct": chemical_saved_pct
    }

if __name__ == "__main__":
    # Self-check
    test_ndvi = calculate_ndvi(0.6, 0.2)
    assert test_ndvi == 0.5, f"Expected 0.5, got {test_ndvi}"
    res = evaluate_crop_health(ndvi_score=0.28, detected_symptom="yellow_rust", field_area_ha=3.0)
    assert res["recommended_action"] == "DISPATCH_VRT_SPRAY"
    assert res["chemical_saved_pct"] == 70.0
    print("[OK] Crop diagnostic logic verified.")
