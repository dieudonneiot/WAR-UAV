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
client.loiter()
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

## Loiter

Use loiter when you want the aircraft to stop following the current route and
circle near its current position:

```powershell
python scripts/loiter.py
```

Like `emergency_rtl.py`, this command first asks the running mission process to
send `LOITER` through its existing MAVLink connection. If no mission process is
running, it falls back to direct MAVLink:

```powershell
python scripts/loiter.py --direct
```

If you intentionally created a second MAVProxy output, point the direct command
at that output:

```powershell
python scripts/loiter.py --direct --connection udpin:0.0.0.0:14551
```

## Live Telemetry

Use the telemetry script to watch the latest mission phase, requested flight
mode, position, altitude, waypoint distance, and data age:

```powershell
python scripts/telemetry.py
```

When `run_square_mission.py` is already running, telemetry is served through the
same local command server as RTL/LOITER. That avoids binding to MAVLink port
`14550` twice.

Useful options:

```powershell
python scripts/telemetry.py --interval-s 0.5
python scripts/telemetry.py --count 10
python scripts/telemetry.py --direct
```

## AUTO Mission Upload

`GUIDED` mode sends one live reposition command per waypoint from the Python
mission loop. `AUTO` mode works differently: Python uploads the full mission to
ArduPlane, switches the aircraft to `AUTO`, arms it, and ArduPlane executes the
mission internally.

Use AUTO mode like this:

```powershell
python scripts/run_square_mission.py --control-mode auto --shape square --size-m 500 --alt-m 50
```

The uploaded mission contains:

```text
NAV_TAKEOFF
NAV_WAYPOINT for each generated shape waypoint
NAV_RETURN_TO_LAUNCH
```

Useful AUTO options:

```powershell
python scripts/run_square_mission.py --control-mode auto --shape circle --size-m 600
python scripts/run_square_mission.py --control-mode auto --auto-monitor-s 0
```

The local RTL, LOITER, and telemetry scripts keep working while AUTO mode is
running because they talk to the mission process instead of trying to bind to
MAVLink port `14550`.

## Interactive Control Panel

Use the terminal control panel when you want one place for common live commands:

```powershell
python scripts/control_panel.py
```

Commands:

```text
status / s        print latest telemetry
rtl / r           return to launch and stop the mission route
loiter / l        loiter near current position and stop the mission route
mode <name>       switch to an ArduPlane mode, for example mode AUTO
auto              shortcut for mode AUTO
guided            shortcut for mode GUIDED
fbwa              shortcut for mode FBWA
takeoff           shortcut for mode TAKEOFF
quit / q          close the panel
```

Like the standalone RTL, LOITER, and telemetry scripts, the panel talks to the
running mission process first. If no mission process is available, it falls back
to direct MAVLink:

```powershell
python scripts/control_panel.py --direct
```

## Web Dashboard

Use the browser dashboard when you want point-and-click controls:

```powershell
python scripts/web_dashboard.py
```

Then open:

```text
http://127.0.0.1:8787
```

The dashboard polls mission status once per second and provides controls for:

```text
TAKEOFF
GUIDED
LOITER
RTL
MODE <custom mode>
```

It talks to the same local mission command server as the terminal tools, so the
running mission keeps ownership of MAVLink port `14550`.

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
3. Loiter command. Done.
4. Live telemetry printout. Done.
5. Waypoint upload using AUTO mode. Done.
6. Interactive keyboard control panel. Done.
7. Web dashboard with TAKEOFF, GUIDED, RTL, LOITER, and status controls. Done.
