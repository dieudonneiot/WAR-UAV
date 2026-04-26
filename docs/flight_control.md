# Flight Control Notes

This project controls ArduPlane SITL through MAVLink. The Python code should
prefer high-level aircraft commands instead of raw stick overrides, because
ArduPlane already handles fixed-wing stabilization, takeoff, navigation,
failsafes, and return-to-launch behavior.

## Control Surfaces

### MAVProxy console

Use MAVProxy for quick manual testing:

```text
mode TAKEOFF
mode GUIDED
mode RTL
mode LOITER
arm throttle
disarm
param set ARMING_CHECK 0
```

This is useful for mode checks, parameter sanity checks, arming, RTL, and
debugging SITL state.

### Python mission scripts

The live MAVLink mission starts at:

```text
scripts/run_square_mission.py
```

The main control helpers are:

```text
src/uav/mavlink/client.py
src/uav/autonomy/navigator.py
```

Important Python operations:

```python
client.set_mode("TAKEOFF")
client.set_mode("GUIDED")
client.set_mode("RTL")
client.arm()
client.reposition(lat_e7, lon_e7, alt_m)
client.get_position()
```

## Emergency RTL

The active mission script has a built-in emergency path:

```powershell
python scripts/run_square_mission.py
```

Press `Ctrl+C` in that same PowerShell window to switch the aircraft to `RTL`.
The script catches the interrupt, sends `RTL`, waits briefly so the command is
processed, and then exits.

There is also a standalone command:

```powershell
python scripts/emergency_rtl.py
```

By default, the running mission opens a local emergency command server on
`127.0.0.1:8765`. The standalone script tries that local command server first,
so it does not need to bind to MAVLink port `14550` while the mission is already
using it.

The fallback path is direct MAVLink. Use it when no mission script is running:

```powershell
python scripts/emergency_rtl.py --direct
```

If you intentionally created a second MAVProxy output, point the direct command
at that output:

```powershell
python scripts/emergency_rtl.py --direct --connection udpin:0.0.0.0:14551
```

## Key ArduPlane Modes

```text
MANUAL   Direct pilot control
FBWA     Stabilized manual fixed-wing flying
TAKEOFF  Automatic takeoff
GUIDED   Programmatic point-to-point control
AUTO     Runs uploaded mission waypoints
RTL      Return to launch
LOITER   Circle around a location
CRUISE   Assisted cruising
```

For this repo, the safest default sequence is:

```text
connect
wait for heartbeat
set simulation parameters
TAKEOFF
arm
wait until target altitude is reached
GUIDED
send waypoints
RTL
```

## Things MAVLink Can Control

The mission computer can command:

```text
Flight mode
Arming/disarming
Takeoff
Return-to-launch
Target location
Target altitude
Waypoint sequence
Loiter/hold behavior
Mission upload
Speed parameters
Throttle parameters
Geofence behavior
Camera/gimbal commands, if hardware is added
Telemetry reading
Failsafe behavior
```

Useful telemetry:

```text
Latitude and longitude
Relative altitude
Ground speed
Airspeed
Heading
Battery
Flight mode
Arming state
Distance to waypoint
Roll, pitch, yaw
GPS status
System status
```

## Avoid Raw RC Control Unless Needed

Raw RC overrides can be sent, but they are easy to misuse with a fixed-wing
aircraft because throttle, pitch, roll, yaw, airspeed, altitude, and stall
prevention must all be coordinated. For most autonomy work, command the
aircraft at the mission level: take off, go to a point, loiter, or return home.

## Next Implementation Steps

1. CLI mission shape selection: square, triangle, circle, line. Done.
2. Emergency RTL command. Done.
3. Loiter command.
4. Live telemetry printout.
5. Waypoint upload using AUTO mode.
6. Interactive keyboard control panel.
7. Web dashboard with TAKEOFF, GUIDED, RTL, LOITER, and status controls.
