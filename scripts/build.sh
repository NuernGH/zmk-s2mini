#!/usr/bin/env bash
# Builds the ZMK firmware for the S2 mini. Usage:
#   scripts/build.sh <workspace-dir> [shield ...]
# The workspace must already be set up with west update (see .github/workflows/build.yml).
# Output: <workspace>/out/<shield>-0x0.bin (flash at 0x0) and <shield>-0x1000.bin.
set -euo pipefail

WS=$(cd "$1" && pwd); shift
MODULE=$(cd "$(dirname "$0")/.." && pwd)
SHIELDS=("$@")
[ ${#SHIELDS[@]} -eq 0 ] && SHIELDS=(s2mini_60)

cd "$WS"
export ZEPHYR_BASE="$WS/zephyr"

# ZMK patch (new USB stack). Skipped if already applied.
if git -C zmk apply --check "$MODULE/patches/zmk-usb-next.patch" 2>/dev/null; then
  git -C zmk apply "$MODULE/patches/zmk-usb-next.patch"
fi

mkdir -p out
for shield in "${SHIELDS[@]}"; do
  west build -p -d "build-$shield" -s zmk/app -b esp32s2_lolin_mini -- \
    -DZephyr_DIR="$ZEPHYR_BASE/share/zephyr-package/cmake" \
    -DZMK_EXTRA_MODULES="$MODULE" \
    -DSHIELD="s2mini_usb $shield"
  cp "build-$shield/zephyr/zmk.bin" "out/$shield-0x1000.bin"
  # Image to flash from address 0x0: 4 KB of 0xFF, then the app
  python3 -c "import sys; d=open(sys.argv[1],'rb').read(); open(sys.argv[2],'wb').write(b'\xff'*0x1000+d)" \
    "out/$shield-0x1000.bin" "out/$shield-0x0.bin"
done
( cd out && sha256sum *.bin > SHA256SUMS )
ls -l out
