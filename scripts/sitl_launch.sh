#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TEKNOFEST 2026 — launch ArduPlane SITL + Gazebo for one session
#
# Usage (from WSL2 terminal):
#   bash scripts/sitl_launch.sh
#   bash scripts/sitl_launch.sh --headless      # no Gazebo GUI
#   bash scripts/sitl_launch.sh --port 14550    # override MAVLink UDP port
#
# What this does:
#   1. Starts Gazebo with the air_defense world (GUI via WSLg)
#   2. Waits for Gazebo to be ready
#   3. Detects the Windows host IP so SITL can send UDP back to Windows Python
#   4. Starts ArduPlane SITL with the gazebo-zephyr model
#   5. Prints the MAVLink connection string for your Python scripts
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ARDUPILOT_DIR="${ARDUPILOT_DIR:-$HOME/ardupilot}"
ARDUPILOT_GAZEBO_DIR="${ARDUPILOT_GAZEBO_DIR:-$HOME/ardupilot_gazebo}"
TEKNOFEST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORLD_FILE="$TEKNOFEST_DIR/config/gazebo/air_defense.sdf"
SITL_HOME="-35.363262,149.165237,584,353"   # Canberra (ArduPilot default)
MAVLINK_PORT=14550
HEADLESS=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --headless) HEADLESS=true ;;
    --port) MAVLINK_PORT="$2"; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
  shift
done

# ── Environment ───────────────────────────────────────────────────────────────
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$ARDUPILOT_GAZEBO_DIR/models:$ARDUPILOT_GAZEBO_DIR/worlds:$TEKNOFEST_DIR/config/gazebo"
export PATH="$PATH:$ARDUPILOT_DIR/Tools/autotest"

# ── Windows host IP (for UDP back to Windows Python) ─────────────────────────
WINDOWS_IP=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
if [[ -z "$WINDOWS_IP" ]]; then
  WINDOWS_IP="127.0.0.1"
fi
echo "[sitl] Windows host IP : $WINDOWS_IP"
echo "[sitl] MAVLink port    : $MAVLINK_PORT"
echo "[sitl] World           : $WORLD_FILE"

# ── Cleanup on exit ───────────────────────────────────────────────────────────
GZ_PID=""
SITL_PID=""
cleanup() {
  echo "[sitl] Shutting down…"
  [[ -n "$SITL_PID" ]] && kill "$SITL_PID" 2>/dev/null || true
  [[ -n "$GZ_PID"   ]] && kill "$GZ_PID"   2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── 1. Start Gazebo ───────────────────────────────────────────────────────────
if $HEADLESS; then
  echo "[sitl] Starting Gazebo (headless)…"
  gz sim -v 4 -r -s "$WORLD_FILE" &
else
  echo "[sitl] Starting Gazebo (GUI via WSLg)…"
  gz sim -v 4 -r "$WORLD_FILE" &
fi
GZ_PID=$!

# Wait for Gazebo transport to come up (poll /world/air_defense/stats)
echo "[sitl] Waiting for Gazebo world to be ready…"
for i in $(seq 1 30); do
  if gz topic -l 2>/dev/null | grep -q "/world/air_defense"; then
    echo "[sitl] Gazebo ready (attempt $i)."
    break
  fi
  sleep 1
done

# ── 2. Start ArduPlane SITL ───────────────────────────────────────────────────
echo "[sitl] Starting ArduPlane SITL…"
cd "$ARDUPILOT_DIR"

sim_vehicle.py \
  -v ArduPlane \
  --model=gazebo-zephyr \
  -f zephyr_delta_wing \
  --no-rebuild \
  --no-mavproxy \
  -l "$SITL_HOME" \
  --out "udpout:$WINDOWS_IP:$MAVLINK_PORT" \
  --out "udpout:127.0.0.1:14551" \
  -S 1 &
SITL_PID=$!

echo ""
echo "══════════════════════════════════════════════════════"
echo "  SITL + Gazebo running."
echo ""
echo "  Connect your Python script with:"
echo "    connection = \"udpin:0.0.0.0:$MAVLINK_PORT\""
echo ""
echo "  Press Ctrl+C to stop everything."
echo "══════════════════════════════════════════════════════"

wait "$SITL_PID"
