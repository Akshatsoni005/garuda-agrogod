"""
Garuda AgroGod - Central Complex (CX) Ring Attractor & Path Integration Test Suite
Verifies:
1. Ellipsoid Body (EB) 16-wedge bump formation and population vector decoding
2. Protocerebral Bridge (PB) Left/Right P-EN shifter response to angular velocity
3. Ring neuron visual cue anchoring and phase locking
4. Fan-Shaped Body (FB) 16-column phasor vector path integration on closed loops
5. PFL3 descending steering circuit for GPS-denied return-to-home
6. Official MAVLink #331 ODOMETRY packet formatting
7. 60s head-to-head flight benchmark proving >90% drift reduction over naive dead reckoning
"""

import sys
import os
import math
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.central_complex import (
    CentralComplexRingAttractor,
    FanShapedBodyPathIntegrator,
    PFL3SteeringCircuit,
    BiologicalNavigationSystem,
    run_gps_denied_flight_benchmark
)


def test_eb_ring_attractor_bump_formation():
    print("[1/7] Testing Ellipsoid Body (EB) 16-Wedge Bump Formation...")
    eb = CentralComplexRingAttractor(num_wedges=16)
    eb.reset_to_heading(math.radians(90.0)) # Heading East / 90 deg

    heading = eb.decode_heading()
    metrics = eb.get_bump_metrics()

    assert abs(math.degrees(heading) - 90.0) < 1.0
    assert metrics["coherence"] > 0.80
    assert len(eb.r) == 16
    print(f"  ✓ Bump formed: Decoded {math.degrees(heading):.1f}° | Coherence: {metrics['coherence'] * 100:.1f}%")


def test_angular_velocity_integration_tracking():
    print("[2/7] Testing Angular Velocity Integration & P-EN Shifter Circuits...")
    eb = CentralComplexRingAttractor(num_wedges=16)
    eb.reset_to_heading(0.0)

    # 1. Turn clockwise at 1.0 rad/s for 1.0 second (expected heading ~= 1.0 rad)
    dt = 0.05
    for _ in range(20):
        eb.step(dt=dt, angular_velocity_rad_s=1.0)
    
    cw_heading = eb.decode_heading()
    assert abs(cw_heading - 1.0) < 0.1
    assert np.max(eb.pen_right) > np.max(eb.pen_left)
    print(f"  ✓ Clockwise yaw: Decoded {cw_heading:.2f} rad (expected 1.00) | P-EN Right Active: {np.max(eb.pen_right):.2f}")

    # 2. Turn counter-clockwise at -1.0 rad/s for 1.0 second (expected heading back to ~0.0)
    for _ in range(20):
        eb.step(dt=dt, angular_velocity_rad_s=-1.0)
    
    ccw_heading = eb.decode_heading()
    diff = (ccw_heading + math.pi) % (2 * math.pi) - math.pi
    assert abs(diff) < 0.1
    assert np.max(eb.pen_left) > np.max(eb.pen_right)
    print(f"  ✓ Counter-clockwise yaw: Returned to {ccw_heading:.2f} rad | P-EN Left Active: {np.max(eb.pen_left):.2f}")


def test_visual_cue_phase_anchoring():
    print("[3/7] Testing Ring Neuron Visual Cue Phase Anchoring...")
    eb = CentralComplexRingAttractor(num_wedges=16)
    eb.reset_to_heading(0.0)

    # Subject ring to an instantaneous visual landmark cue at 180 degrees (pi rad)
    target_cue = math.pi
    for _ in range(10):
        eb.step(dt=0.05, angular_velocity_rad_s=0.0, visual_cue_heading=target_cue)
    
    locked_heading = eb.decode_heading()
    assert abs(locked_heading - math.pi) < 0.1
    print(f"  ✓ Phase locked to visual anchor: {math.degrees(locked_heading):.1f}° (Target: 180.0°)")


def test_fan_shaped_body_closed_loop_path_integration():
    print("[4/7] Testing Fan-Shaped Body (FB) Closed-Loop Vector Path Integration...")
    fb = FanShapedBodyPathIntegrator(num_columns=16)

    dt = 0.1
    speed = 2.0 # m/s
    steps_per_leg = 25 # 2.5 seconds * 2.0 m/s = 5.0 meters per leg

    # Leg 1: East (heading = 0.0 rad)
    for _ in range(steps_per_leg):
        fb.step(dt=dt, heading_rad=0.0, v_forward_m_s=speed)
    
    # Leg 2: North (heading = pi/2 rad)
    for _ in range(steps_per_leg):
        fb.step(dt=dt, heading_rad=math.pi / 2.0, v_forward_m_s=speed)

    # Leg 3: West (heading = pi rad)
    for _ in range(steps_per_leg):
        fb.step(dt=dt, heading_rad=math.pi, v_forward_m_s=speed)

    # Leg 4: South (heading = 3pi/2 rad)
    for _ in range(steps_per_leg):
        fb.step(dt=dt, heading_rad=1.5 * math.pi, v_forward_m_s=speed)

    home_vec = fb.get_home_vector()
    assert home_vec["home_distance_m"] < 0.15 # Returned to origin within 15 cm
    print(f"  ✓ Closed square loop residual error: {home_vec['home_distance_m'] * 100:.2f} cm (Expected < 15 cm)")


def test_pfl3_steering_homing():
    print("[5/7] Testing PFL3 Descending Steering Circuit...")
    pfl3 = PFL3SteeringCircuit(gain=1.5, max_yaw_rate_rad_s=1.2)

    # Current heading is North (90 deg), Home is South (270 deg)
    current_h = math.radians(90.0)
    target_b = math.radians(270.0)

    steer = pfl3.compute_steering(current_h, target_b)
    assert abs(steer) > 0.5
    print(f"  ✓ PFL3 steering torque generated: {steer:+.2f} rad/s")


def test_mavlink_odometry_packet():
    print("[6/7] Testing MAVLink #331 ODOMETRY Telemetry Generation...")
    bio_nav = BiologicalNavigationSystem()
    bio_nav.step(dt=0.1, gyro_z_rad_s=0.05, forward_speed_m_s=3.0)

    pkt = bio_nav.generate_mavlink_odometry_packet(alt_m=14.5)
    assert pkt["mavlink_msg"] == "ODOMETRY"
    assert pkt["msgid"] == 331
    assert pkt["z"] == -14.5 # NED down
    assert len(pkt["q"]) == 4
    assert pkt["quality_pct"] >= 80
    print(f"  ✓ Valid MAVLink #331 packet: NED Pos=({pkt['x']}, {pkt['y']}, {pkt['z']}) | Quality={pkt['quality_pct']}%")


def test_gps_denied_flight_benchmark():
    print("[7/7] Testing Full 60s GPS-Denied Drone Flight Benchmark...")
    res = run_gps_denied_flight_benchmark(
        flight_duration_s=60.0,
        wind_gust_strength=0.6,
        mag_drift_deg_per_min=45.0,
        gyro_bias_rad_s=0.02
    )

    s = res["benchmark_summary"]
    assert s["drift_reduction_pct"] > 90.0
    assert s["homing_success"] is True
    assert s["final_biological_drift_m"] < 5.0
    assert s["final_dead_reckoning_drift_m"] > 35.0
    print(f"  ✓ Naive Dead Reckoning Drift: {s['final_dead_reckoning_drift_m']:.2f} m")
    print(f"  ✓ Biological CX Attractor Drift: {s['final_biological_drift_m']:.2f} m")
    print(f"  ✓ Net Drift Error Reduction: {s['drift_reduction_pct']}% | Homing Success: {s['homing_success']}")


if __name__ == "__main__":
    test_eb_ring_attractor_bump_formation()
    test_angular_velocity_integration_tracking()
    test_visual_cue_phase_anchoring()
    test_fan_shaped_body_closed_loop_path_integration()
    test_pfl3_steering_homing()
    test_mavlink_odometry_packet()
    test_gps_denied_flight_benchmark()
    print("\n==================================================================")
    print("  [SUCCESS] 8/7 BIOLOGICAL CENTRAL COMPLEX TESTS PASSED! (100%)  ")
    print("==================================================================")
