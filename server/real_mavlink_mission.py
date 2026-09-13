"""
Garuda AgroGod - Real Official ArduPilot/PX4 MAVLink 2.0 Mission Engine
Uses official pymavlink library to construct standard MAVLink protocol packets
for autonomous precision agriculture spray missions.
"""

import math
from typing import List, Dict, Any, Tuple
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink2

def create_mavlink_mission_items(
    waypoints: List[Dict[str, Any]],
    target_system: int = 1,
    target_component: int = 1
) -> List[Any]:
    """Generates standard MAVLink 2.0 MISSION_ITEM_INT messages for ArduPilot Copter.
    Encodes exact GPS coordinates in scaled integers (lat * 1e7, lon * 1e7)
    and injects MAV_CMD_DO_SET_SERVO (183) commands for PWM relay actuation.
    """
    items = []
    seq = 0

    # 1. Home / Takeoff Item
    # Command 22 = MAV_CMD_NAV_TAKEOFF
    first_wp = waypoints[0] if waypoints else {"lat": 26.9124, "lon": 75.7873, "alt": 12.0}
    takeoff = mavlink2.MAVLink_mission_item_int_message(
        target_system=target_system,
        target_component=target_component,
        seq=seq,
        frame=mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        command=mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        current=1,
        autocontinue=1,
        param1=0.0, # Minimum pitch
        param2=0.0,
        param3=0.0,
        param4=0.0, # Yaw angle
        x=int(first_wp["lat"] * 1e7),
        y=int(first_wp["lon"] * 1e7),
        z=float(first_wp.get("alt", 12.0)),
        mission_type=mavutil.mavlink.MAV_MISSION_TYPE_MISSION
    )
    items.append(takeoff)
    seq += 1

    # 2. Navigation Waypoints & Actuation Triggers
    prev_spray_state = False

    for wp in waypoints:
        is_spraying = wp.get("spraying", False)
        
        # If spraying state toggles, inject servo PWM command
        # SERVO_PIN 9 (often AUX OUT 1 on Pixhawk for spray solenoid)
        # PWM: 2000us = FULL OPEN (100%), 1000us = CLOSED (0%)
        if is_spraying != prev_spray_state:
            pwm_val = 2000.0 if is_spraying else 1000.0
            servo_cmd = mavlink2.MAVLink_mission_item_int_message(
                target_system=target_system,
                target_component=target_component,
                seq=seq,
                frame=mavutil.mavlink.MAV_FRAME_MISSION,
                command=mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
                current=0,
                autocontinue=1,
                param1=9.0,      # Servo channel 9
                param2=pwm_val,  # PWM pulse width in microseconds
                param3=0.0,
                param4=0.0,
                x=0,
                y=0,
                z=0.0,
                mission_type=mavutil.mavlink.MAV_MISSION_TYPE_MISSION
            )
            items.append(servo_cmd)
            seq += 1
            prev_spray_state = is_spraying

        # Nav Waypoint (MAV_CMD_NAV_WAYPOINT = 16)
        nav_wp = mavlink2.MAVLink_mission_item_int_message(
            target_system=target_system,
            target_component=target_component,
            seq=seq,
            frame=mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            command=mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            current=0,
            autocontinue=1,
            param1=0.0, # Hold time
            param2=1.5, # Acceptance radius in meters
            param3=0.0, # Pass through waypoint
            param4=0.0, # Desired yaw angle
            x=int(wp["lat"] * 1e7),
            y=int(wp["lon"] * 1e7),
            z=float(wp.get("alt", 12.0)),
            mission_type=mavutil.mavlink.MAV_MISSION_TYPE_MISSION
        )
        items.append(nav_wp)
        seq += 1

    # 3. Ensure spray is closed before RTL
    if prev_spray_state:
        servo_off = mavlink2.MAVLink_mission_item_int_message(
            target_system=target_system,
            target_component=target_component,
            seq=seq,
            frame=mavutil.mavlink.MAV_FRAME_MISSION,
            command=mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
            current=0,
            autocontinue=1,
            param1=9.0,
            param2=1000.0, # 1000us = OFF
            param3=0.0,
            param4=0.0,
            x=0,
            y=0,
            z=0.0,
            mission_type=mavutil.mavlink.MAV_MISSION_TYPE_MISSION
        )
        items.append(servo_off)
        seq += 1

    # 4. Return to Launch (MAV_CMD_NAV_RETURN_TO_LAUNCH = 20)
    rtl = mavlink2.MAVLink_mission_item_int_message(
        target_system=target_system,
        target_component=target_component,
        seq=seq,
        frame=mavutil.mavlink.MAV_FRAME_MISSION,
        command=mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
        current=0,
        autocontinue=1,
        param1=0.0,
        param2=0.0,
        param3=0.0,
        param4=0.0,
        x=0,
        y=0,
        z=0.0,
        mission_type=mavutil.mavlink.MAV_MISSION_TYPE_MISSION
    )
    items.append(rtl)

    return items

def serialize_mission_to_qgc_wpl(mission_items: List[Any]) -> str:
    """Exports MAVLink mission items into official QGroundControl WPL 110 format."""
    lines = ["QGC WPL 110"]
    for item in mission_items:
        # Convert scaled ints back to float degrees
        lat = item.x / 1e7 if item.x != 0 else 0.0
        lon = item.y / 1e7 if item.y != 0 else 0.0
        line = f"{item.seq}\t{item.current}\t{item.frame}\t{item.command}\t{item.param1:.6f}\t{item.param2:.6f}\t{item.param3:.6f}\t{item.param4:.6f}\t{lat:.6f}\t{lon:.6f}\t{item.z:.6f}\t{item.autocontinue}"
        lines.append(line)
    return "\n".join(lines)

if __name__ == "__main__":
    sample_wps = [
        {"lat": 26.9124, "lon": 75.7873, "alt": 10.0, "spraying": False},
        {"lat": 26.9126, "lon": 75.7875, "alt": 10.0, "spraying": True},
        {"lat": 26.9128, "lon": 75.7877, "alt": 10.0, "spraying": False}
    ]
    items = create_mavlink_mission_items(sample_wps)
    assert len(items) >= 5 # Takeoff + Navs + Servos + RTL
    wpl = serialize_mission_to_qgc_wpl(items)
    assert "QGC WPL 110" in wpl
    assert "183" in wpl # MAV_CMD_DO_SET_SERVO present
    print("[SUCCESS] Official ArduPilot MAVLink 2.0 Mission Engine verified:")
    print(f"  Generated {len(items)} official MAVLink mission items.")
    print("  Header:", wpl.splitlines()[0])
    print("  Item 0 (Takeoff):", wpl.splitlines()[1])
