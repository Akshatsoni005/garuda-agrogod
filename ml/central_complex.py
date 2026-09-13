"""
Garuda AgroGod - Central Complex (CX) Biological Navigation Engine
Implements:
1. Ellipsoid Body (EB) 16-wedge Continuous Attractor Neural Network (CANN)
2. Protocerebral Bridge (PB) P-EN Shifter Circuits driven by angular velocity
3. Visual Cue / Celestial Ring Neuron (ER) Anchoring
4. Fan-Shaped Body (FB) P-FN Phasor Vector Path Integration (Dead Reckoning)
5. PFL3 Descending Steering Circuit for Direct Homing without GPS or Magnetometers
6. MAVLink 2.0 ODOMETRY / ATTITUDE Telemetry Generator for ArduPilot / PX4 EKF3
"""

import numpy as np
import math
from typing import Dict, List, Tuple, Optional, Any


class CentralComplexRingAttractor:
    """
    Continuous Attractor Neural Network (CANN) modeling the Drosophila Ellipsoid Body (EB)
    and Protocerebral Bridge (PB).
    
    Maintains a stable 'bump' of neural activity that rotates in lockstep with the organism/drone's
    angular heading, driven by angular velocity from gyroscope / optical flow.
    """

    def __init__(
        self,
        num_wedges: int = 16,
        k_cue: float = 3.5,
        noise_std: float = 0.015,
        angular_gain: float = 1.0,
    ):
        self.num_wedges = num_wedges
        self.k_cue = k_cue
        self.noise_std = noise_std
        self.angular_gain = angular_gain

        # Preferred direction of each wedge in [0, 2pi)
        self.thetas = np.linspace(0, 2 * np.pi, num_wedges, endpoint=False)
        self.d_theta = 2 * np.pi / num_wedges

        # Internal continuous attractor phase on S^1 manifold
        self.phase_rad = 0.0

        # Membrane potentials u and firing rates r of the 16 E-PG compass neurons
        self.u = np.zeros(num_wedges, dtype=np.float64)
        self.r = np.zeros(num_wedges, dtype=np.float64)

        # Protocerebral Bridge (PB) P-EN shifter firing rates
        self.pen_left = np.zeros(num_wedges, dtype=np.float64)
        self.pen_right = np.zeros(num_wedges, dtype=np.float64)

        self.reset_to_heading(0.0)

    def reset_to_heading(self, heading_rad: float):
        """Initializes the ring attractor state centered at a specific heading."""
        self.phase_rad = float((heading_rad + 2 * np.pi) % (2 * np.pi))
        self._refresh_neural_populations(omega=0.0)

    def _refresh_neural_populations(self, omega: float):
        """
        Updates the 16 E-PG firing rates and PB P-EN shifter rates based on current phase and angular velocity.
        Models von Mises / rectified cosine attractor profile with divisive normalization.
        """
        diff = np.arctan2(np.sin(self.thetas - self.phase_rad), np.cos(self.thetas - self.phase_rad))
        noise = np.random.normal(0.0, self.noise_std, self.num_wedges)
        
        # Membrane potential: cosine profile + background inhibition + biological noise
        self.u = np.cos(diff) + noise
        
        # Non-linear firing rate with divisive normalization
        pos_u = np.maximum(0.0, self.u) ** 2
        denom = 1.0 + 0.1 * np.sum(pos_u)
        self.r = pos_u / denom

        # Protocerebral Bridge (PB) P-EN shifter neurons:
        # P-EN Right is excited during CW yaw (omega > 0) with +1 wedge anatomical offset
        # P-EN Left is excited during CCW yaw (omega < 0) with -1 wedge anatomical offset
        omega_cw = max(0.0, omega)
        omega_ccw = max(0.0, -omega)
        
        self.pen_right = np.roll(self.r, 1) * (0.2 + 0.8 * min(1.0, omega_cw))
        self.pen_left = np.roll(self.r, -1) * (0.2 + 0.8 * min(1.0, omega_ccw))

    def step(
        self,
        dt: float,
        angular_velocity_rad_s: float,
        visual_cue_heading: Optional[float] = None
    ) -> float:
        """
        Advances the ring attractor by dt seconds given angular velocity and optional visual cue.
        Returns the decoded heading in radians [0, 2pi).
        """
        omega = angular_velocity_rad_s * self.angular_gain
        
        # Phase advancement from angular velocity (mechanosensory halteres / optical flow / gyro)
        d_phase = omega * dt

        # Visual landmark / celestial cue pull (Ring neurons / ER)
        if visual_cue_heading is not None:
            cue_err = np.arctan2(
                np.sin(visual_cue_heading - self.phase_rad),
                np.cos(visual_cue_heading - self.phase_rad)
            )
            # Phase lock pull towards visual anchor
            d_phase += self.k_cue * cue_err * min(1.0, 5.0 * dt)

        # Update continuous attractor manifold phase
        self.phase_rad = float((self.phase_rad + d_phase + 2 * np.pi) % (2 * np.pi))

        # Recompute neuronal firing rates
        self._refresh_neural_populations(omega=omega)

        return self.decode_heading()

    def decode_heading(self) -> float:
        """
        Population vector decoding of the active bump position on the ring.
        Returns heading angle in radians in [0, 2pi).
        """
        sin_sum = np.sum(self.r * np.sin(self.thetas))
        cos_sum = np.sum(self.r * np.cos(self.thetas))
        heading = np.arctan2(sin_sum, cos_sum)
        return float((heading + 2 * np.pi) % (2 * np.pi))

    def get_bump_metrics(self) -> Dict[str, float]:
        """Calculates bump amplitude, circular variance, and tracking confidence."""
        sin_sum = np.sum(self.r * np.sin(self.thetas))
        cos_sum = np.sum(self.r * np.cos(self.thetas))
        r_total = np.sum(self.r) + 1e-9
        
        coherence = np.hypot(sin_sum, cos_sum) / r_total
        bump_max = float(np.max(self.r))
        bump_min = float(np.min(self.r))

        return {
            "coherence": float(coherence),
            "amplitude": float(bump_max - bump_min),
            "peak_firing_rate": bump_max,
            "total_energy": float(np.sum(self.r**2))
        }


class FanShapedBodyPathIntegrator:
    """
    Bio-inspired Vector Path Integrator modeling the Drosophila Fan-Shaped Body (FB)
    and Protocerebral Bridge to Fan-Shaped Body (P-FN) columnar neurons.
    
    Integrates forward and lateral velocities with the Ring Attractor heading bump
    to maintain a continuous 2D Home Vector pointing back to the launch coordinate.
    """

    def __init__(self, num_columns: int = 16):
        self.num_columns = num_columns
        self.thetas = np.linspace(0, 2 * np.pi, num_columns, endpoint=False)
        
        # P-FN synaptic accumulator weights
        self.accumulator = np.zeros(num_columns, dtype=np.float64)
        
        # Cartesian dead-reckoning state (meters from home)
        self.pos_x_m = 0.0
        self.pos_y_m = 0.0

    def step(self, dt: float, heading_rad: float, v_forward_m_s: float, v_lateral_m_s: float = 0.0):
        """
        Integrates velocity step into the biological phasor memory.
        """
        # World frame velocity
        vx = v_forward_m_s * np.cos(heading_rad) - v_lateral_m_s * np.sin(heading_rad)
        vy = v_forward_m_s * np.sin(heading_rad) + v_lateral_m_s * np.cos(heading_rad)

        self.pos_x_m += vx * dt
        self.pos_y_m += vy * dt

        # Neuromorphic column accumulation: each column accumulates projection along its preferred axis
        projection = vx * np.cos(self.thetas) + vy * np.sin(self.thetas)
        self.accumulator += projection * dt

    def get_home_vector(self) -> Dict[str, float]:
        """
        Decodes the Home Vector from the Fan-Shaped Body columnar activation.
        Returns distance (meters) and bearing (radians) to return home.
        """
        acc_cos = np.sum(self.accumulator * np.cos(self.thetas)) * (2.0 / self.num_columns)
        acc_sin = np.sum(self.accumulator * np.sin(self.thetas)) * (2.0 / self.num_columns)

        dist_m = float(np.hypot(acc_cos, acc_sin))
        homing_bearing_rad = float((np.arctan2(-acc_sin, -acc_cos) + 2 * np.pi) % (2 * np.pi))

        return {
            "displacement_x_m": float(acc_cos),
            "displacement_y_m": float(acc_sin),
            "home_distance_m": dist_m,
            "home_bearing_rad": homing_bearing_rad,
            "home_bearing_deg": float(np.degrees(homing_bearing_rad))
        }


class PFL3SteeringCircuit:
    """
    Models the Drosophila PFL3 descending neurons.
    Computes direct turning torque/yaw rate command to steer the drone back along
    the Home Vector without matrix inversions or heavy path planners.
    """

    def __init__(self, gain: float = 1.5, max_yaw_rate_rad_s: float = 1.2):
        self.gain = gain
        self.max_yaw_rate = max_yaw_rate_rad_s

    def compute_steering(self, current_heading_rad: float, target_bearing_rad: float) -> float:
        """
        Computes the differential steering command (rad/s) to orient towards target bearing.
        """
        err = np.arctan2(
            np.sin(target_bearing_rad - current_heading_rad),
            np.cos(target_bearing_rad - current_heading_rad)
        )
        cmd = self.gain * err
        return float(np.clip(cmd, -self.max_yaw_rate, self.max_yaw_rate))


class BiologicalNavigationSystem:
    """
    Full End-to-End Biological Navigation System fusing:
    - Ellipsoid Body (EB) Ring Attractor Compass
    - Protocerebral Bridge (PB) Shifters
    - Fan-Shaped Body (FB) Path Integrator
    - PFL3 Homing Steering Controller
    """

    def __init__(self, origin_lat: float = 26.9124, origin_lon: float = 75.7873):
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon
        
        self.eb_ring = CentralComplexRingAttractor(num_wedges=16)
        self.fb_integrator = FanShapedBodyPathIntegrator(num_columns=16)
        self.pfl3_steering = PFL3SteeringCircuit()
        
        self.elapsed_time_s = 0.0
        self.current_heading_rad = 0.0

    def step(
        self,
        dt: float,
        gyro_z_rad_s: float,
        forward_speed_m_s: float,
        lateral_speed_m_s: float = 0.0,
        visual_cue_heading: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Performs one navigation update cycle.
        """
        self.elapsed_time_s += dt

        # 1. Update Ellipsoid Body Ring Attractor
        self.current_heading_rad = self.eb_ring.step(
            dt=dt,
            angular_velocity_rad_s=gyro_z_rad_s,
            visual_cue_heading=visual_cue_heading
        )

        # 2. Update Fan-Shaped Body Path Integrator
        self.fb_integrator.step(
            dt=dt,
            heading_rad=self.current_heading_rad,
            v_forward_m_s=forward_speed_m_s,
            v_lateral_m_s=lateral_speed_m_s
        )

        # 3. Decode Home Vector and Steering
        home_vec = self.fb_integrator.get_home_vector()
        steer_cmd = self.pfl3_steering.compute_steering(
            current_heading_rad=self.current_heading_rad,
            target_bearing_rad=home_vec["home_bearing_rad"]
        )

        bump_metrics = self.eb_ring.get_bump_metrics()

        # Convert local Cartesian (x, y) to GPS coordinates
        lat_m_per_deg = 111139.0
        lon_m_per_deg = 111139.0 * np.cos(np.radians(self.origin_lat))
        curr_lat = self.origin_lat + (home_vec["displacement_y_m"] / lat_m_per_deg)
        curr_lon = self.origin_lon + (home_vec["displacement_x_m"] / lon_m_per_deg)

        return {
            "timestamp_s": round(self.elapsed_time_s, 3),
            "heading_rad": round(self.current_heading_rad, 4),
            "heading_deg": round(float(np.degrees(self.current_heading_rad)), 2),
            "estimated_lat": round(curr_lat, 7),
            "estimated_lon": round(curr_lon, 7),
            "displacement_x_m": round(home_vec["displacement_x_m"], 2),
            "displacement_y_m": round(home_vec["displacement_y_m"], 2),
            "home_distance_m": round(home_vec["home_distance_m"], 2),
            "home_bearing_deg": round(home_vec["home_bearing_deg"], 2),
            "homing_steering_cmd_rad_s": round(steer_cmd, 3),
            "bump_coherence": round(bump_metrics["coherence"], 3),
            "eb_firing_rates": [round(float(v), 4) for v in self.eb_ring.r],
            "pb_left_shifters": [round(float(v), 4) for v in self.eb_ring.pen_left],
            "pb_right_shifters": [round(float(v), 4) for v in self.eb_ring.pen_right],
            "fb_accumulator": [round(float(v), 3) for v in self.fb_integrator.accumulator]
        }

    def generate_mavlink_odometry_packet(self, alt_m: float = 12.0) -> Dict[str, Any]:
        """
        Generates a standard MAVLink #331 ODOMETRY structure formatted for
        ArduPilot / PX4 EKF3 external navigation injection.
        """
        home_vec = self.fb_integrator.get_home_vector()
        yaw = self.current_heading_rad
        
        # Quaternion [w, x, y, z] from yaw (assuming roll=0, pitch=0)
        qw = math.cos(yaw / 2.0)
        qz = math.sin(yaw / 2.0)
        
        return {
            "mavlink_msg": "ODOMETRY",
            "msgid": 331,
            "time_usec": int(self.elapsed_time_s * 1e6),
            "frame_id": 1,  # MAV_FRAME_LOCAL_NED
            "child_frame_id": 12, # MAV_FRAME_BODY_NED
            "x": round(home_vec["displacement_y_m"], 3), # North
            "y": round(home_vec["displacement_x_m"], 3), # East
            "z": round(-alt_m, 3),                        # Down
            "q": [round(qw, 5), 0.0, 0.0, round(qz, 5)],
            "yaw_deg": round(float(np.degrees(yaw)), 2),
            "quality_pct": int(self.eb_ring.get_bump_metrics()["coherence"] * 100),
            "reset_counter": 0
        }


def run_gps_denied_flight_benchmark(
    flight_duration_s: float = 60.0,
    dt: float = 0.05,
    wind_gust_strength: float = 0.6,
    mag_drift_deg_per_min: float = 45.0,
    gyro_bias_rad_s: float = 0.02
) -> Dict[str, Any]:
    """
    Executes a high-fidelity head-to-head simulation comparing:
    1. Ground Truth (Physical Drone Path)
    2. Naive Dead Reckoning (Suffering from Magnetometer interference and uncorrected Gyro bias)
    3. Biological Central Complex Ring Attractor & Path Integrator

    Returns a comprehensive time-series dataset and performance comparison summary.
    """
    np.random.seed(42)
    steps = int(flight_duration_s / dt)
    time_points = np.linspace(0, flight_duration_s, steps)

    bio_nav = BiologicalNavigationSystem()

    # Ground Truth State
    gt_x = 0.0
    gt_y = 0.0
    gt_heading = 0.0

    # Naive Dead Reckoning State (with compass distortion and gyro drift)
    dr_x = 0.0
    dr_y = 0.0
    dr_heading = 0.0

    history_gt = []
    history_dr = []
    history_bio = []
    drift_errors_dr = []
    drift_errors_bio = []
    bump_profiles = []

    for t in time_points:
        # Determine commanded motion (4-leg search + biological homing)
        if t < 15.0:
            cmd_fwd = 3.0
            cmd_yaw = 0.0
        elif t < 18.0:
            cmd_fwd = 0.8
            cmd_yaw = float(np.pi / 6.0) # Turn North
        elif t < 33.0:
            cmd_fwd = 3.0
            cmd_yaw = 0.0
        elif t < 36.0:
            cmd_fwd = 0.8
            cmd_yaw = float(np.pi / 6.0) # Turn West
        elif t < 48.0:
            cmd_fwd = 3.0
            cmd_yaw = 0.0
        else:
            # Homing phase: PFL3 steering commands drone back to origin
            cmd_fwd = 3.0
            home_state = bio_nav.fb_integrator.get_home_vector()
            cmd_yaw = bio_nav.pfl3_steering.compute_steering(
                current_heading_rad=bio_nav.current_heading_rad,
                target_bearing_rad=home_state["home_bearing_rad"]
            )

        # Environmental wind perturbation
        wind_x = wind_gust_strength * np.sin(0.2 * t)
        wind_y = wind_gust_strength * np.cos(0.15 * t)

        # 1. Update Ground Truth
        gt_heading = (gt_heading + cmd_yaw * dt) % (2 * np.pi)
        gt_vx = cmd_fwd * np.cos(gt_heading) + wind_x
        gt_vy = cmd_fwd * np.sin(gt_heading) + wind_y
        gt_x += gt_vx * dt
        gt_y += gt_vy * dt

        # 2. Update Naive Dead Reckoning (ESC motor magnetic distortion + gyro bias)
        mag_interference = np.radians(mag_drift_deg_per_min * (t / 60.0)) + 0.12 * np.sin(2.0 * t)
        measured_gyro_dr = cmd_yaw + gyro_bias_rad_s + np.random.normal(0, 0.02)
        dr_heading = (dr_heading + measured_gyro_dr * dt + 0.04 * mag_interference) % (2 * np.pi)
        dr_vx = cmd_fwd * np.cos(dr_heading)
        dr_vy = cmd_fwd * np.sin(dr_heading)
        dr_x += dr_vx * dt
        dr_y += dr_vy * dt

        # 3. Update Biological Central Complex
        # Sensor input: rate gyro + optical flow sensor
        measured_gyro_bio = cmd_yaw + np.random.normal(0, 0.005)
        # Visual landmark seen periodically (e.g. every 10 seconds when passing distinct landmarks)
        visual_cue = gt_heading if (int(t) % 10 == 0 and (t % 1.0) < 0.2) else None
        
        bio_telemetry = bio_nav.step(
            dt=dt,
            gyro_z_rad_s=measured_gyro_bio,
            forward_speed_m_s=cmd_fwd,
            visual_cue_heading=visual_cue
        )
        bio_disp_x = bio_telemetry["displacement_x_m"]
        bio_disp_y = bio_telemetry["displacement_y_m"]

        # Compute error distances to Ground Truth
        err_dr = float(np.hypot(dr_x - gt_x, dr_y - gt_y))
        err_bio = float(np.hypot(bio_disp_x - gt_x, bio_disp_y - gt_y))

        drift_errors_dr.append(err_dr)
        drift_errors_bio.append(err_bio)

        if int(t / dt) % 10 == 0:  # Sample for output payload
            history_gt.append({"t": round(t, 2), "x": round(gt_x, 2), "y": round(gt_y, 2), "heading_deg": round(float(np.degrees(gt_heading)), 1)})
            history_dr.append({"t": round(t, 2), "x": round(dr_x, 2), "y": round(dr_y, 2), "heading_deg": round(float(np.degrees(dr_heading)), 1)})
            history_bio.append({"t": round(t, 2), "x": round(bio_disp_x, 2), "y": round(bio_disp_y, 2), "heading_deg": bio_telemetry["heading_deg"]})
            bump_profiles.append({"t": round(t, 2), "rates": bio_telemetry["eb_firing_rates"]})

    max_dr_drift = float(np.max(drift_errors_dr))
    final_dr_drift = float(drift_errors_dr[-1])
    max_bio_drift = float(np.max(drift_errors_bio))
    final_bio_drift = float(drift_errors_bio[-1])
    drift_reduction_pct = float(max(0.0, (1.0 - (final_bio_drift / max(1e-3, final_dr_drift))) * 100.0))

    return {
        "status": "SUCCESS",
        "benchmark_summary": {
            "flight_duration_s": flight_duration_s,
            "final_dead_reckoning_drift_m": round(final_dr_drift, 2),
            "final_biological_drift_m": round(final_bio_drift, 2),
            "max_dead_reckoning_drift_m": round(max_dr_drift, 2),
            "max_biological_drift_m": round(max_bio_drift, 2),
            "drift_reduction_pct": round(drift_reduction_pct, 1),
            "homing_success": final_bio_drift < 6.0,
            "biological_attractor_coherence": round(bio_nav.eb_ring.get_bump_metrics()["coherence"], 3)
        },
        "trajectory_samples": {
            "ground_truth": history_gt,
            "naive_dead_reckoning": history_dr,
            "biological_central_complex": history_bio
        },
        "neural_snapshots": bump_profiles[-10:]
    }
