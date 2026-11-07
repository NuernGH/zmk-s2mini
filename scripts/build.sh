#!/usr/bin/env bash
# Buduje firmware ZMK dla S2 mini. Użycie:
#   scripts/build.sh <katalog-workspace> [shield ...]
# Workspace musi już mieć west update (zob. .github/workflows/build.yml).
# Wynik: <workspace>/out/<shield>-0x0.bin (do wgrania pod 0x0) i <shield>-0x1000.bin.
set -euo pipefail

WS=$(cd "$1" && pwd); shift
MODULE=$(cd "$(dirname "$0")/.." && pwd)
SHIELDS=("$@")
[ ${#SHIELDS[@]} -eq 0 ] && SHIELDS=(s2mini_60 s2mini_zmk_test)

cd "$WS"
export ZEPHYR_BASE="$WS/zephyr"

# Łatka ZMK (nowy stos USB). Pomijana, jeśli już nałożona.
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
  # Obraz do wgrania od adresu 0x0: 4 KB 0xFF, potem program
  python3 -c "import sys; d=open(sys.argv[1],'rb').read(); open(sys.argv[2],'wb').write(b'\xff'*0x1000+d)" \
    "out/$shield-0x1000.bin" "out/$shield-0x0.bin"
done
( cd out && sha256sum *.bin > SHA256SUMS )
ls -l out
