# IDX Fundamental Analyzer - one-shot bootstrap untuk Windows PowerShell.
#
# Cara pakai:
#   1. Buka PowerShell, cd ke folder project.
#   2. Kalau pertama kali jalankan script PS1 di laptop ini, jalankan sekali:
#         Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   3. Jalankan: .\setup.ps1
#
# Yang di-handle:
#   - Verifikasi Python >= 3.10 ada di PATH.
#   - Bikin virtual env di .venv (skip kalau sudah ada).
#   - Aktifkan venv + upgrade pip + install requirements.txt.
#   - Smoke test cepat: import paket + run unit tests.

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[X]  $msg" -ForegroundColor Red }

# --- 1. Cek Python ---
Write-Step "Cek instalasi Python..."
try {
    $pythonVersion = & python --version 2>&1
} catch {
    Write-Err "Python tidak ditemukan di PATH."
    Write-Host "   Install Python 3.10+ dari https://www.python.org/downloads/"
    Write-Host "   Saat install, centang 'Add Python to PATH'."
    exit 1
}

if ($pythonVersion -notmatch "Python (\d+)\.(\d+)") {
    Write-Err "Tidak bisa parse versi Python: $pythonVersion"
    exit 1
}
$major = [int]$Matches[1]
$minor = [int]$Matches[2]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Err "Butuh Python 3.10+, terdeteksi: $pythonVersion"
    exit 1
}
Write-Ok "Python OK: $pythonVersion"

# --- 2. Buat virtual env ---
Write-Step "Setup virtual environment di .venv ..."
if (Test-Path ".\.venv\Scripts\python.exe") {
    Write-Ok ".venv sudah ada, skip pembuatan."
} else {
    & python -m venv .venv
    if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
        Write-Err "Gagal membuat .venv."
        exit 1
    }
    Write-Ok ".venv dibuat."
}

# Pakai python.exe dari venv langsung, lebih reliable daripada Activate.
$venvPy = ".\.venv\Scripts\python.exe"

# --- 3. Upgrade pip + install dependencies ---
Write-Step "Upgrade pip..."
& $venvPy -m pip install --upgrade pip --quiet

Write-Step "Install dependencies dari requirements.txt..."
if (-not (Test-Path "requirements.txt")) {
    Write-Err "requirements.txt tidak ditemukan. Pastikan Anda di folder project."
    exit 1
}
& $venvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install gagal. Cek koneksi internet / proxy / firewall."
    exit 1
}
Write-Ok "Dependencies ter-install."

# --- 4. Smoke test: import paket utama ---
Write-Step "Smoke test: import paket utama..."
$smokeCode = @"
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
"@
& $venvPy -c $smokeCode
if ($LASTEXITCODE -ne 0) {
    Write-Err "Smoke test gagal."
    exit 1
}
Write-Ok "Semua paket bisa di-import."

# --- 5. Run unit tests (offline, no network) ---
Write-Step "Run unit tests..."
& $venvPy -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Beberapa test gagal. Tetap lanjut, tapi mohon dicek."
} else {
    Write-Ok "Semua unit test PASS."
}

# --- 6. Selesai ---
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Setup selesai. Cara pakai:" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1                 # aktifkan venv"
Write-Host "  python analyze.py --emiten BBCA              # contoh single emiten"
Write-Host "  python analyze.py                            # pakai watchlist default"
Write-Host "  python analyze.py --emiten BBCA --export pdf # export PDF"
Write-Host ""
