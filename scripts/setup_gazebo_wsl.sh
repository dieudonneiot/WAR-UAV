#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TEKNOFEST 2026 — Gazebo + ArduPilot SITL one-time setup (run inside WSL2)
#
# Usage (from WSL2 terminal):
#   chmod +x setup_gazebo_wsl.sh && ./setup_gazebo_wsl.sh
#
# What this installs:
#   • Gazebo Harmonic  (gz-sim 8.x)
#   • ardupilot_gazebo plugin  (ArduPilot ↔ Gazebo bridge)
#   • ArduPilot + sim_vehicle.py
#   • MAVProxy
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ARDUPILOT_DIR="$HOME/ardupilot"
ARDUPILOT_GAZEBO_DIR="$HOME/ardupilot_gazebo"
TEKNOFEST_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "══════════════════════════════════════════════════════"
echo "  TEKNOFEST Gazebo + SITL setup"
echo "  ArduPilot  → $ARDUPILOT_DIR"
echo "  az_gazebo  → $ARDUPILOT_GAZEBO_DIR"
echo "══════════════════════════════════════════════════════"

# ── 1. System packages ────────────────────────────────────────────────────────
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  git curl wget lsb-release gnupg ca-certificates \
  python3-pip python3-dev \
  cmake build-essential ninja-build \
  rapidjson-dev

# ── 2. Gazebo Harmonic ────────────────────────────────────────────────────────
if ! command -v gz &>/dev/null; then
  echo "[setup] Installing Gazebo Harmonic…"
  sudo curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
    -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
    http://packages.osrfoundation.org/gazebo/ubuntu-stable \
    $(lsb_release -cs) main" \
    | sudo tee /etc/apt/sources.list.d/gazebo-stable.list
  sudo apt-get update -qq
  sudo apt-get install -y gz-harmonic
  echo "[setup] Gazebo Harmonic installed."
else
  echo "[setup] Gazebo already installed: $(gz sim --version 2>&1 | head -1)"
fi

# ── 3. ardupilot_gazebo plugin ────────────────────────────────────────────────
if [[ ! -d "$ARDUPILOT_GAZEBO_DIR" ]]; then
  echo "[setup] Cloning ardupilot_gazebo…"
  git clone https://github.com/ArduPilot/ardupilot_gazebo.git "$ARDUPILOT_GAZEBO_DIR"
fi

cd "$ARDUPILOT_GAZEBO_DIR"
git pull --quiet

mkdir -p build && cd build
cmake .. -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
ninja -j"$(nproc)"
sudo ninja install

# Set env vars in ~/.bashrc if not already present
for line in \
  "export GZ_SIM_SYSTEM_PLUGIN_PATH=\$GZ_SIM_SYSTEM_PLUGIN_PATH:\$(gz sim --plugin-path 2>/dev/null | head -1)" \
  "export GZ_SIM_RESOURCE_PATH=\$GZ_SIM_RESOURCE_PATH:$ARDUPILOT_GAZEBO_DIR/models:$ARDUPILOT_GAZEBO_DIR/worlds:$TEKNOFEST_DIR/config/gazebo"
do
  grep -qxF "$line" ~/.bashrc || echo "$line" >> ~/.bashrc
done

echo "[setup] ardupilot_gazebo plugin built and installed."

# ── 4. ArduPilot + SITL ───────────────────────────────────────────────────────
if [[ ! -d "$ARDUPILOT_DIR" ]]; then
  echo "[setup] Cloning ArduPilot (full repo, takes a few minutes)…"
  git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git "$ARDUPILOT_DIR"
fi

cd "$ARDUPILOT_DIR"
git pull --quiet
git submodule update --init --recursive --quiet

# Install ArduPilot python dependencies
pip3 install --user -r requirements.txt 2>/dev/null || true
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile

# Build ArduPlane SITL
./waf configure --board sitl
./waf plane

echo "[setup] ArduPlane SITL built."

# ── 5. MAVProxy ───────────────────────────────────────────────────────────────
pip3 install --user MAVProxy

# ── 6. Verify ────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  Setup complete. Verify:"
echo "    gz sim --version"
echo "    $ARDUPILOT_DIR/build/sitl/bin/arduplane --version"
echo "══════════════════════════════════════════════════════"
echo ""
echo "  Next step — open a new WSL2 terminal and run:"
echo "    bash $TEKNOFEST_DIR/scripts/sitl_launch.sh"
echo ""
