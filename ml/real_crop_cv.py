"""
Garuda AgroGod - Yellow-Lesion Candidate Detector using HSV thresholding (ExG + hue band).
Detects yellow-colored pixels on green vegetation as spray candidates.
NOT a trained disease classifier — false positives include senescence, nutrient deficiency, dust.
Requires UAV visual confirmation.
"""

import cv2
import numpy as np
from typing import Dict, Any, List, Tuple

def compute_excess_green_index(bgr_image: np.ndarray) -> np.ndarray:
    """Computes Excess Green Index (ExG): ExG = 2*G - R - B.
    Widely cited standard in agricultural computer vision (Woebbecke et al.)
    to separate living green canopy from soil and crop residue.
    """
    b, g, r = cv2.split(bgr_image.astype(np.float32))
    exg = 2.0 * g - r - b
    # Normalize to 0-255 uint8
    exg_norm = cv2.normalize(exg, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return exg_norm

def detect_foliar_pathology_and_triggers(
    bgr_image: np.ndarray,
    ground_speed_m_s: float = 3.0,
    camera_to_nozzle_offset_m: float = 0.6
) -> Dict[str, Any]:
    """Analyzes a crop canopy image for fungal blight / yellow rust lesions.
    Calculates exact millisecond solenoid valve opening delay and duration.
    """
    h, w, _ = bgr_image.shape
    total_pixels = h * w
    
    # 1. Segment canopy using Excess Green
    exg = compute_excess_green_index(bgr_image)
    _, canopy_mask = cv2.threshold(exg, 130, 255, cv2.THRESH_BINARY)
    canopy_pixel_count = cv2.countNonZero(canopy_mask)
    
    if canopy_pixel_count == 0:
        return {
            "has_crop": False,
            "infection_detected": False,
            "solenoid_trigger": False
        }

    # 2. Convert to HSV to detect yellow rust / necrotic brown spots
    hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
    
    # Yellow rust range in HSV (H: 15-35, S: 70-255, V: 70-255)
    lower_yellow = np.array([15, 60, 70])
    upper_yellow = np.array([35, 255, 255])
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    
    # Lesions only count if they are on living leaf canopy
    lesion_mask = cv2.bitwise_and(yellow_mask, yellow_mask, mask=canopy_mask)
    lesion_pixels = cv2.countNonZero(lesion_mask)
    
    infection_ratio = float(lesion_pixels / max(canopy_pixel_count, 1))
    infection_pct = round(infection_ratio * 100.0, 2)
    
    # Find contours and bounding boxes of diseased clusters
    contours, _ = cv2.findContours(lesion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bounding_boxes = []
    for c in contours:
        if cv2.contourArea(c) > 25: # filter sensor noise
            bx, by, bw, bh = cv2.boundingRect(c)
            bounding_boxes.append({
                "x": int(bx), "y": int(by), "w": int(bw), "h": int(bh),
                "area_px": int(cv2.contourArea(c))
            })

    # 3. Compute Physical Solenoid Timing
    # t_delay = offset_distance / ground_speed
    should_spray = infection_pct > 1.5 or len(bounding_boxes) > 0
    
    if should_spray and ground_speed_m_s > 0.1:
        trigger_delay_ms = int(round((camera_to_nozzle_offset_m / ground_speed_m_s) * 1000))
        # Pulse duration proportional to lesion density (e.g. 150ms to 400ms)
        pulse_duration_ms = min(400, max(120, int(infection_pct * 40)))
    else:
        trigger_delay_ms = 0
        pulse_duration_ms = 0

    return {
        "canopy_coverage_pct": round((canopy_pixel_count / total_pixels) * 100.0, 1),
        "infection_detected": should_spray,
        "infection_severity_pct": infection_pct,
        "lesion_cluster_count": len(bounding_boxes),
        "bounding_boxes": bounding_boxes[:10], # Top 10 clusters
        "physical_actuation": {
            "solenoid_active": should_spray,
            "flight_speed_m_s": ground_speed_m_s,
            "trigger_delay_ms": trigger_delay_ms,
            "pulse_duration_ms": pulse_duration_ms,
            "recommended_pwm_duty_cycle": min(100, int(infection_pct * 15 + 40)) if should_spray else 0
        }
    }

def create_synthetic_crop_image(h: int = 400, w: int = 400) -> np.ndarray:
    """Generates a realistic test frame: dark soil background, green leaf canopy,
    and a distinct yellow-rust fungal outbreak patch.
    """
    # Soil background: dark brownish-gray
    img = np.full((h, w, 3), (35, 45, 55), dtype=np.uint8)
    
    # Draw green crop leaves
    cv2.ellipse(img, (200, 200), (120, 60), 30, 0, 360, (30, 140, 40), -1)
    cv2.ellipse(img, (220, 180), (100, 50), -45, 0, 360, (25, 160, 45), -1)
    
    # Inject yellow rust fungal pustules
    cv2.circle(img, (210, 190), 18, (30, 210, 230), -1) # Yellow BGR
    cv2.circle(img, (230, 175), 12, (25, 190, 220), -1)
    
    return img

if __name__ == "__main__":
    test_frame = create_synthetic_crop_image()
    results = detect_foliar_pathology_and_triggers(
        test_frame,
        ground_speed_m_s=3.0,
        camera_to_nozzle_offset_m=0.6
    )
    assert results["infection_detected"] is True
    assert results["physical_actuation"]["solenoid_active"] is True
    assert results["physical_actuation"]["trigger_delay_ms"] == 200 # 0.6 / 3.0 = 0.2s = 200ms
    print("[SUCCESS] Real Computer Vision Module verified:")
    print(f"  Canopy Coverage: {results['canopy_coverage_pct']}%")
    print(f"  Infection Severity: {results['infection_severity_pct']}%")
    print(f"  Trigger Delay: {results['physical_actuation']['trigger_delay_ms']} ms")
    print(f"  Pulse Duration: {results['physical_actuation']['pulse_duration_ms']} ms")
    print(f"  PWM Duty Cycle: {results['physical_actuation']['recommended_pwm_duty_cycle']}%")
