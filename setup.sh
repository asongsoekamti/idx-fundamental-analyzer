#!/usr/bin/env bash
# IDX Fundamental Analyzer - one-shot bootstrap untuk macOS / Linux.
#
# Cara pakai:
#   chmod +x setup.sh
#   ./setup.sh
#
# Yang di-handle:
#   - Verifikasi Python >= 3.10.
#   - Bikin virtual env di .venv (skip kalau sudah ada).
#   - Install requirements.txt.
#   - Smoke test import + run unit tests.

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { printf "${CYAN}==> %s${NC}\n" "$*"; }
ok()   { printf "${GREEN}[OK] %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}[!]  %s${NC}\n" "$*"; }
err()  { printf "${RED}[X]  %s${NC}\n" "$*"; }

# Pilih binary python: prefer python3, fallback python.
PYTHON_BIN=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYTHON_BIN="$cand"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    err "Python tidak ditemukan di PATH."
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# --- 1. Cek versi ---
step "Cek instalasi Python..."
PY_VERSION=$($PYTHON_BIN --version 2>&1)
PY_MAJOR=$($PYTHON_BIN -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PYTHON_BIN -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    err "Butuh Python 3.10+, terdeteksi: $PY_VERSION"
    exit 1
fi
ok "Python OK: $PY_VERSION"

# --- 2. Buat virtual env ---
step "Setup virtual environment di .venv ..."
if [ -x ".venv/bin/python" ]; then
    ok ".venv sudah ada, skip pembuatan."
else
    $PYTHON_BIN -m venv .venv
    if [ ! -x ".venv/bin/python" ]; then
        err "Gagal membuat .venv. Di Ubuntu/Debian biasanya butuh:"
        echo "  sudo apt install python3-venv"
        exit 1
    fi
    ok ".venv dibuat."
fi

VENV_PY=".venv/bin/python"

# --- 3. Upgrade pip + install ---
step "Upgrade pip..."
$VENV_PY -m pip install --upgrade pip --quiet

step "Install dependencies dari requirements.txt..."
if [ ! -f "requirements.txt" ]; then
    err "requirements.txt tidak ditemukan. Pastikan Anda di folder project."
    exit 1
fi
$VENV_PY -m pip install -r requirements.txt
ok "Dependencies ter-install."

# --- 4. Smoke test ---
step "Smoke test: import paket utama..."
$VENV_PY - <<'PY'
import importlib, sys
mods = ['yfinance', 'pandas', 'numpy', 'reportlab', 'analyzer']
missing = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        missing.append(f'{m}: {type(e).__name__}: {e}')
if missing:
    print('FAIL:')
    for x in missing:
        print('  ' + x)
    sys.exit(1)
print('All imports OK')
PY
ok "Semua paket bisa di-import."

# --- 5. Run unit tests ---
step "Run unit tests..."
if $VENV_PY -m unittest discover -s tests; then
    ok "Semua unit test PASS."
else
    warn "Beberapa test gagal. Tetap lanjut, tapi mohon dicek."
fi

# --- 6. Selesai ---
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} Setup selesai. Cara pakai:${NC}"
echo -e "${GREEN}============================================================${NC}"
echo "  source .venv/bin/activate                     # aktifkan venv"
echo "  python analyze.py --emiten BBCA              # contoh single emiten"
echo "  python analyze.py                            # pakai watchlist default"
echo "  python analyze.py --emiten BBCA --export pdf # export PDF"
echo ""
