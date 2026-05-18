# IDX Fundamental Analyzer

Aplikasi Python untuk analisis fundamental saham yang listed di **Bursa Efek Indonesia (IDX/BEI)**. Fokus utama pada **MOS (Margin of Safety), ROE, ROA, PEG, PBV**, plus puluhan rasio fundamental lain.

Data diambil dari **Yahoo Finance** (gratis, suffix `.JK`), dengan caching lokal supaya tidak terus-menerus hit API.

> **v0.3** - **banking-aware valuation**. Saham bank otomatis pakai DDM + Justified PBV (bukan FCF DCF). Plus quality floor: ROE < 12% akan downgrade verdict ke HOLD regardless of MOS.
>
> **v0.2** - **CLI text-based** (`analyze.py`) lengkap dengan scoring otomatis dan export TXT/PDF. Streamlit dashboard (`app.py`) tetap ada sebagai pilihan UI tambahan.

---

## 1. Apa yang Bisa Dihitung

### Metrik utama (fokus user)

| Metrik | Sumber | Catatan |
|---|---|---|
| **MOS (Margin of Safety)** | Dihitung dari Graham Number & DCF | Positif = saham undervalued |
| **ROE** (Return on Equity) | yfinance `returnOnEquity`, fallback: Net Income / Equity | |
| **ROA** (Return on Assets) | yfinance `returnOnAssets`, fallback: Net Income / Assets | |
| **PEG** (P/E to Growth) | yfinance `pegRatio` / `trailingPegRatio` | < 1 sering dianggap menarik |
| **PBV** (Price to Book Value) | yfinance `priceToBook`, fallback: Price / BVPS | |

### Metrik tambahan yang juga dihitung otomatis

Aplikasi ini menghitung **~70 metrik fundamental** dari list 100 yang Anda berikan. Berikut ringkasannya:

**Profitabilitas**: Revenue, Gross/Operating/Net Profit, EBITDA, Gross/Operating/Net/EBITDA Margin, EPS, Forward EPS, COGS, Cash Flow Margin

**Return**: ROA, ROE, ROIC (NOPAT/IC dengan asumsi tax 22%), ROI (proxy)

**Valuasi**: PER, Forward PER, PBV, PSR, PEG, EV/EBITDA, EV/Sales, Book Value per Share, Tangible Book Value

**Pertumbuhan**: Revenue Growth YoY, Earnings Growth YoY, EPS Growth, Operating Income Growth, Asset Growth, Equity Growth, Revenue CAGR 3Y/5Y, Net Income CAGR 3Y

**Likuiditas**: Current Ratio, Quick Ratio, Cash Ratio, Working Capital, Working Capital Ratio

**Leverage**: DER, Debt to Asset, Total Debt, Net Debt, Net Debt/EBITDA, Interest Coverage

**Cash Flow**: Operating CF, Free CF, CapEx, CapEx to Revenue

**Efisiensi**: Asset Turnover, Inventory/Receivable/Payable Turnover, DSO, DIO, DPO, Cash Conversion Cycle

**Struktur Biaya**: SG&A Ratio, Operating Expense Ratio, R&D to Revenue

**Dividen**: Dividend Yield, Payout Ratio, Dividend Rate

**Konsistensi & Risiko**: Net Margin Stability (stdev), Margin Expansion Trend, Beta, Insider/Institutional Ownership, Share Dilution Rate, Market Cap, Enterprise Value, Retained Earnings

### Yang **TIDAK** bisa diambil dari yfinance

Metrik berikut dari list Anda **tidak tersedia di Yahoo Finance** untuk saham Indonesia dan butuh sumber lain (laporan IDX/OJK, scraping Stockbit, atau API berbayar seperti Sectors.id):

- **Rasio khusus bank**: NPL, LAR, NIM, LDR, CAR, BOPO, CIR, NII, Fee Based Income, Fee Income Ratio, CASA Ratio, Credit/Deposit Growth, Loan Yield, Cost of Fund, Spread Interest, LCR, NSFR, Provision Coverage Ratio, Write-off Ratio, RWA, Coverage of NPA
- **Kualitatif**: Economic Moat, Pricing Power
- **Forecast analyst**: Earnings Surprise, Analyst Growth Forecast (limited)
- **Free Float Ratio**, **Share Buyback Rate** (hanya proxy via share dilution)

Kalau Anda butuh metrik perbankan, saya bisa tambahkan modul scraper IDX/OJK terpisah — beritahu saja.

---

## 2. Arsitektur

```
idx-fundamental-analyzer/
│
├── app.py                      # Streamlit dashboard (entry point)
├── requirements.txt
├── README.md
├── .gitignore
│
├── analyzer/                   # Core library
│   ├── __init__.py
│   ├── fetcher.py             # Lapisan ambil data (yfinance + disk cache)
│   ├── metrics.py             # Hitung semua rasio fundamental
│   ├── valuation.py           # Graham Number, DCF, MOS
│   └── screener.py            # Batch screening + composite score
│
├── data/
│   └── cache/                 # Auto-generated cache (JSON + parquet)
│
└── examples/
    └── watchlist.csv          # Contoh watchlist 30 saham populer IDX
```

**Flow data**:

```
User input ticker
       │
       ▼
┌──────────────┐    cache hit?    ┌──────────────┐
│  fetcher.py  │ ───────────────► │  data/cache  │
│ (yfinance)   │ ◄─────────────── │  (JSON+pq)   │
└──────┬───────┘   cache miss     └──────────────┘
       │
       ▼
┌──────────────┐
│  metrics.py  │  → dict ~70 metrik
└──────┬───────┘
       │
       ├──────────────────────┐
       ▼                      ▼
┌──────────────┐      ┌──────────────┐
│ valuation.py │      │ screener.py  │
│ Graham + DCF │      │ Batch + rank │
│ → MOS        │      │              │
└──────┬───────┘      └──────┬───────┘
       │                     │
       └─────────┬───────────┘
                 ▼
        ┌──────────────┐
        │   app.py     │  Streamlit UI
        │  (dashboard) │  + export CSV
        └──────────────┘
```

---

## 3. Migrasi ke Laptop Baru (Pindahin Project ke PC Pribadi)

Inti yang perlu dipahami: **yang dipindah cuma source code dan watchlist**. Folder `.venv/`, `data/cache/`, dan `reports/` **TIDAK** perlu di-copy - akan di-regenerate di laptop baru.

### Yang DIPINDAH vs yang TIDAK

| Pindah ✓ | Skip ✗ |
|---|---|
| `analyze.py`, `app.py` (kalau pakai) | `.venv/` (rebuild di lokasi baru) |
| `analyzer/` (semua .py) | `__pycache__/` (auto-generated) |
| `tests/` | `data/cache/` (regenerate dari yfinance) |
| `examples/watchlist.csv` (+ watchlist custom Anda) | `reports/` (output Anda) |
| `requirements.txt`, `README.md`, `.gitignore` | File `.pyc` apapun |
| `setup.ps1`, `setup.sh` | |

Total ukuran "yang penting" cuma ±200 KB. Folder `.venv/` di laptop lama bisa 1-2 GB, jadi penting di-skip.

### Langkah migrasi

#### Opsi A - via Git (paling rapi, anti-corrupt, sekalian backup)

Di laptop lama:

```powershell
cd C:\Users\andreaha\Documents\idx-fundamental-analyzer

# Bikin repo lokal kalau belum
git init
git add .
git commit -m "Initial CLI version"

# Push ke GitHub privat (bikin repo kosong dulu di github.com)
git remote add origin https://github.com/USERNAME/idx-fundamental-analyzer.git
git branch -M main
git push -u origin main
```

Di laptop baru:

```powershell
cd $HOME\Documents
git clone https://github.com/USERNAME/idx-fundamental-analyzer.git
cd idx-fundamental-analyzer
.\setup.ps1                # auto bikin venv + install + run tests
```

#### Opsi B - via ZIP / USB / cloud drive (kalau tidak mau pakai git)

Di laptop lama (PowerShell):

```powershell
cd $HOME\Documents

# Bikin archive yang exclude .venv & cache (hemat 1-2 GB)
$exclude = @('.venv', '__pycache__', 'data\cache', 'reports', '*.pyc', '*.log')
$tmpStaging = "$env:TEMP\idx-staging"
robocopy idx-fundamental-analyzer $tmpStaging /E /XD .venv __pycache__ data\cache reports /XF *.pyc *.log | Out-Null
Compress-Archive -Path $tmpStaging\* -DestinationPath idx-fundamental-analyzer.zip -Force
Remove-Item -Recurse -Force $tmpStaging
```

Pindahkan `idx-fundamental-analyzer.zip` ke laptop baru (USB / OneDrive / Google Drive / WhatsApp Self-Chat).

Di laptop baru:

```powershell
cd $HOME\Documents
Expand-Archive idx-fundamental-analyzer.zip -DestinationPath idx-fundamental-analyzer
cd idx-fundamental-analyzer
.\setup.ps1
```

#### Opsi C - copy-paste folder via Network Drive / OneDrive Sync

Pastikan exclude `.venv/` saat copy. Di Windows Explorer:

1. Buka folder `idx-fundamental-analyzer`.
2. Select All (`Ctrl+A`), lalu hold `Ctrl` dan klik untuk **deselect** folder `.venv`, `__pycache__`, dan `data\cache` kalau ada.
3. Copy ke lokasi baru.
4. Di lokasi baru: jalankan `.\setup.ps1`.

### Bootstrap otomatis dengan `setup.ps1` / `setup.sh`

Project sudah include script bootstrap satu-shot. Setelah source code ada di laptop baru:

**Windows:**

```powershell
# Sekali saja kalau PowerShell tolak script (execution policy)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

cd $HOME\Documents\idx-fundamental-analyzer
.\setup.ps1
```

**macOS / Linux:**

```bash
cd ~/Documents/idx-fundamental-analyzer
chmod +x setup.sh
./setup.sh
```

Script akan otomatis:

1. Verifikasi `python --version` >= 3.10.
2. Buat `.venv/` (kalau belum ada).
3. Upgrade pip.
4. `pip install -r requirements.txt`.
5. Smoke test import paket (`yfinance`, `pandas`, `numpy`, `reportlab`, `analyzer`).
6. Run unit tests (`unittest discover -s tests`).

Kalau ada step yang gagal, script akan stop dengan pesan error yang jelas.

### Sebelum migrasi - checklist di laptop baru

| Komponen | Cara cek | Kalau belum ada |
|---|---|---|
| **Python 3.10+** | `python --version` | Download dari https://www.python.org/downloads/. **Centang "Add Python to PATH"** saat install. |
| **pip** | `python -m pip --version` | Sudah otomatis ada di Python 3.10+ |
| **PowerShell execution policy** (Windows) | `Get-ExecutionPolicy` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| **Git** (kalau pakai opsi A) | `git --version` | https://git-scm.com/download |
| **Internet** | `ping yahoo.com` | yfinance + pip butuh akses internet |

### Verifikasi instalasi

Setelah `setup.ps1` selesai, run:

```powershell
.\.venv\Scripts\Activate.ps1
python analyze.py --emiten BBCA.JK
```

Output diharapkan: muncul header `[1/1] Mengambil BBCA.JK ... OK (X.Xs) - <verdict>` lalu blok lengkap section Profitability/Growth/Valuation/Risk/Score. Kalau hang lebih dari 30 detik di "Mengambil...", besar kemungkinan masalah firewall/proxy ke Yahoo Finance.

### Common pitfalls + cara fix

| Masalah | Penyebab | Fix |
|---|---|---|
| `python : command not found` | Python belum ter-install / belum di PATH | Reinstall, centang "Add Python to PATH". Atau pakai `py -3.10` di Windows. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | PS execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, lalu ulangi |
| `pip install` lambat / timeout | Proxy korporat / koneksi lemot | Pakai `pip install --proxy http://USER:PASS@HOST:PORT -r requirements.txt`, atau pindah ke jaringan rumah |
| `ModuleNotFoundError: No module named 'analyzer'` | Run python dari folder lain | `cd` dulu ke folder project sebelum run, atau pakai full path `python C:\path\analyze.py` |
| `error: Microsoft Visual C++ 14.0 or greater is required` | Beberapa lib (jarang kejadian dengan wheel sekarang) butuh compiler | Install Visual Studio Build Tools, atau pakai Python yang resmi dari python.org (bukan dari Microsoft Store) |
| Output `MOS: N/A` / `Intrinsic Value: N/A` untuk semua emiten | Cache stale dari laptop lama, atau yfinance lagi rate-limit | Clear cache: `Remove-Item -Recurse data\cache\*`, atau pakai `--no-cache` |
| Tests gagal di test_cli `test_export_txt_produces_summary_and_detail` | reportlab belum ke-install | `pip install reportlab>=4.0.0` |
| `UnicodeEncodeError` saat print di terminal | Codepage Windows lama tidak support UTF-8 | `chcp 65001` di PowerShell, atau pakai Windows Terminal (sudah default UTF-8) |

### Tip portability

- **Pin Python version**: project ini di-test di Python 3.10 - 3.13. Hindari Python 3.14+ sampai dependency utama (yfinance, reportlab) confirmed compatible.
- **Jangan commit `.venv/`**: sudah di-handle `.gitignore`.
- **Custom watchlist**: simpan watchlist Anda sendiri di `examples/my_watchlist.csv` - ini ke-track git tapi `data/cache/` tidak.
- **Backup `data/cache/` opsional**: kalau koneksi internet di laptop baru terbatas, copy folder cache supaya bisa langsung running offline pakai data lama (TTL cache default 6 jam, jadi after that akan refetch).

---

## 4. Instalasi (manual, kalau tidak pakai setup script)

### Prasyarat

- **Python 3.10+** (cek dengan `python --version`)
- Koneksi internet (untuk hit Yahoo Finance pertama kali)
- OS: Windows / macOS / Linux

### Langkah Setup (Windows PowerShell)

```powershell
# 1. Masuk ke folder project
cd $env:USERPROFILE\Documents\idx-fundamental-analyzer

# 2. Buat virtual environment (opsional tapi sangat dianjurkan)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

> Kalau `Activate.ps1` ditolak karena execution policy, jalankan sekali:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
> lalu ulangi `Activate.ps1`.

### Setup di macOS / Linux

```bash
cd ~/Documents/idx-fundamental-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 5. Cara Menjalankan

### A. CLI (rekomendasi - text based)

Dari folder project (dengan venv aktif):

```powershell
# Default: pakai watchlist examples/watchlist.csv (max 50 emiten)
python analyze.py

# Single emiten (suffix .JK opsional - otomatis ditambah)
python analyze.py --emiten BBRI.JK

# Beberapa emiten sekaligus
python analyze.py --emiten BBCA,BBRI,TLKM

# Watchlist custom
python analyze.py --watchlist path/to/my_watchlist.csv

# Export ke TXT / PDF / keduanya
python analyze.py --export txt
python analyze.py --export pdf
python analyze.py --export both --output-dir reports

# Override asumsi DCF (non-bank, semua persen)
python analyze.py --emiten ASII --wacc 11 --growth 7 --terminal 3.5

# Override Cost of Equity (untuk saham bank)
python analyze.py --emiten BBCA --coe 11

# Bypass cache (selalu fetch yfinance)
python analyze.py --emiten BBRI --no-cache
```

**Output console** per emiten (rapi, monospaced):

```
================================================================
Ticker: BBCA.JK  -  Bank Central Asia Tbk PT
Financial Services  Banks - Regional
================================================================
Price                  : IDR 9,200
Intrinsic Value        : IDR 12,000  (Blend (Graham+DCF))
MOS                    : 23.33%
Upside                 : 30.43%

--- Profitability ---
ROE                    : 22.00%
ROA                    : 3.50%
Net Margin             : 35.00%
Operating Margin       : 42.00%

--- Growth ---
Revenue Growth (YoY)   : 8.00%
Net Income Growth (YoY): 10.00%
Revenue CAGR 5Y        : 9.50%
FCF Growth (proxy 5Y)  : 9.50%

--- Valuation ---
PER                    : 18.00x
PBV                    : 4.50x
PEG                    : 1.20
Price/FCF              : 15.00x

--- Financial Health ---
DER                    : 0.40
Interest Coverage      : 12.00x
Current Ratio          : 1.80

--- Risk ---
Beta                   : 0.90
Earnings Stability     : High

--- DCF Assumptions ---
WACC (discount)        : 12.0%
Growth (10Y)           : 8.0%
Terminal Growth        : 4.0%

--- Score ---
Quality Score          : 85.0 / 100
Valuation Score        : 78.0 / 100
Risk Score             : 70.0 / 100
Composite              : 77.7
Overall                : BUY [+]
```

Plus **summary table** ASCII di atas saat menganalisis lebih dari 1 emiten:

```
+----------+-----------+-----------+--------+--------+--------+-------+------+------+-------+-----------+
| Ticker   | Price     | IV        | MOS    | Upside | ROE    | PER   | PBV  | DER  | Score | Verdict   |
+----------+-----------+-----------+--------+--------+--------+-------+------+------+-------+-----------+
| BBCA.JK  | IDR 9,200 | IDR 12,000| 23.3%  | 30.4%  | 22.0%  | 18.00 | 4.50 | 0.40 | 77.7  | BUY       |
| BBRI.JK  | IDR 4,900 | IDR 5,500 | 10.9%  | 12.2%  | 18.0%  | 14.00 | 2.30 | 0.55 | 72.5  | ACCUMULATE|
| TLKM.JK  | IDR 2,800 | IDR 3,400 | 17.6%  | 21.4%  | 20.0%  | 13.00 | 2.10 | 0.65 | 75.0  | BUY       |
+----------+-----------+-----------+--------+--------+--------+-------+------+------+-------+-----------+
```

### Catatan penting

- **MOS dihitung konservatif/moderat**: intrinsic value default = rata-rata **Graham + DCF** (kalau keduanya tersedia). Bila hanya satu metode yang valid, dipotong **haircut 10%** sebagai cushion. Lihat `analyzer/scoring.py::conservative_intrinsic_value`.
- **Watchlist max 50 emiten** (hard cap). Kalau file watchlist berisi lebih banyak, hanya 50 baris pertama yang diproses. Bisa diturunkan via `--limit`.
- **Caching**: hasil `yfinance` disimpan di `data/cache/` selama 6 jam (default). Pakai `--no-cache` untuk bypass.

### B. Dashboard Streamlit (legacy, opsional)

Versi web lama tetap tersedia:

```powershell
streamlit run app.py
```

### C. Pakai sebagai library Python

```python
from analyzer import StockFetcher, compute_metrics, intrinsic_value_summary

fetcher = StockFetcher()
data = fetcher.fetch("BBCA")              # auto jadi BBCA.JK
metrics = compute_metrics(data)

print(f"ROE: {metrics['roe']*100:.2f}%")
print(f"PBV: {metrics['pbv']:.2f}")
print(f"PEG: {metrics['peg']}")

val = intrinsic_value_summary(metrics, dcf_growth=0.10, dcf_discount=0.13)
print(f"Graham IV: {val['graham'].intrinsic_value:,.0f}")
print(f"Graham MOS: {val['graham'].margin_of_safety*100:.1f}%")
print(f"DCF IV: {val['dcf'].intrinsic_value:,.0f}")
print(f"DCF MOS: {val['dcf'].margin_of_safety*100:.1f}%")
```

### D. Pakai scoring + report sebagai library

```python
from analyzer import (
    StockFetcher, compute_metrics,
    graham_number, simple_dcf,
    build_scorecard, DcfAssumptions,
    render_stock_section,
)

fetcher = StockFetcher()
data = fetcher.fetch("BBCA")
metrics = compute_metrics(data)

graham = graham_number(metrics["eps"], metrics["book_value_per_share"])
dcf = simple_dcf(metrics["free_cash_flow"], metrics["shares_outstanding"])
sc = build_scorecard(metrics, graham, dcf)

print(f"Verdict   : {sc.verdict}")
print(f"Composite : {sc.composite}")
print(f"MOS       : {sc.mos*100:.2f}%")
print(f"Upside    : {sc.upside*100:.2f}%")

# Atau sekalian render satu blok teks rapi:
print(render_stock_section(metrics, sc, DcfAssumptions()))
```

### E. Screening watchlist via script

```python
from analyzer.screener import screen_watchlist, load_watchlist

tickers = load_watchlist("examples/watchlist.csv")
df = screen_watchlist(tickers)
df.to_excel("hasil_screening.xlsx", index=False)
```

---

## 6. Formula Penting

### Graham Number (intrinsic value konservatif Benjamin Graham)

```
Graham IV = sqrt( 22.5 × EPS × Book Value per Share )
```

Faktor 22.5 = PER max 15 × PBV max 1.5. **Hanya valid** untuk perusahaan dengan EPS > 0 dan ekuitas positif.

### Margin of Safety

```
MOS = (Intrinsic Value − Harga Pasar) / Intrinsic Value
```

- MOS = +30% → harga 30% di bawah intrinsic (menarik)
- MOS = -10% → harga 10% di atas intrinsic (overvalued)

Benjamin Graham biasanya minta MOS ≥ 33%, sementara value investor modern sering 20-25%.

### Simple DCF (dua tahap)

```
1. Proyeksikan FCF tahun 1-10 dengan growth_rate
2. Hitung PV tiap tahun: FCF_t / (1 + r)^t
3. Terminal Value (Gordon): FCF_11 / (r − g_terminal)
4. Equity Value = ΣPV + PV(TV) + Cash − Debt
5. Intrinsic per share = Equity Value / Shares Outstanding
```

### Banking Valuation (DDM + Justified PBV)

FCF DCF tidak cocok untuk bank: capex bank sebagian besar berupa loans/deposit,
sehingga "FCF" Yahoo Finance sering nol/negatif dan menghasilkan IV yang
mis-leading rendah. Sebagai gantinya, untuk saham bank kita pakai blend
50/50 dari dua model klasik (Damodaran):

```
DDM:
  intrinsic_ddm = DPS / (cost_of_equity - growth)

Justified P/BV:
  pbv_fair      = (ROE - growth) / (cost_of_equity - growth)
  intrinsic_pbv = pbv_fair * BVPS

Final:
  intrinsic_value = 0.5 * intrinsic_ddm + 0.5 * intrinsic_pbv

Asumsi:
  growth          = min(ROE * (1 - payout_ratio), 0.10)
  cost_of_equity  = 10% (default; override via --coe)
  payout_ratio    = 40% (default jika yfinance tidak menyediakan)
  DPS fallback    = EPS * payout_ratio (bila dividend_rate kosong)
```

Detection: kalau `sector` atau `industry` mengandung kata kunci `bank`,
banking model otomatis dipakai. Cek `analyzer/banking.py::is_banking_stock`.

Validation tambahan: **`Quality Floor`**. Bila ROE < 12% (`ROE_DOWNGRADE_THRESHOLD`),
verdict di-cap ke HOLD bahkan kalau MOS-nya tinggi - karena bank dengan ROE
di bawah cost of equity yang wajar bukan investasi yang menarik meski terlihat
"murah".

Untuk non-bank, jalur Graham + DCF lama tetap dipakai (lihat di bawah).

### Composite Score (Screener legacy)

Rata-rata persentil dari: ROE ↑, ROIC ↑, MOS Graham ↑, PER ↓, DER ↓, PEG ↓ (positif).

### CLI Score (`analyze.py`)

Lebih absolut (tidak persentil), gampang dibaca:

| Skor | Bahan | Range |
|---|---|---|
| **Quality** | ROE, ROA, Net Margin, Margin Stability | 0-100 |
| **Valuation** | PER, PBV, PEG, MOS | 0-100 |
| **Risk** | DER, Current Ratio, Interest Coverage, Beta, Earnings Stability | 0-100 (lebih tinggi = lebih aman) |
| **Composite** | rata-rata 3 di atas | 0-100 |

**Verdict**:

| Verdict | Syarat |
|---|---|
| **BUY** | Composite ≥ 75 dan MOS ≥ 15% |
| **ACCUMULATE** | Composite ≥ 65 dan MOS ≥ 5% |
| **HOLD** | Composite ≥ 50 |
| **REDUCE** | Composite ≥ 35 atau MOS < -10% |
| **SELL** | Composite < 35 atau MOS < -25% |

> **Catatan**: skor ini cuma untuk **sortir watchlist**. Bukan rekomendasi beli/jual.

---

## 7. Testing

Project pakai modul `unittest` standar (no extra deps). Dari root project dengan venv aktif:

```powershell
python -m unittest discover -s tests -v
```

Test yang ada:

- `tests/test_scoring.py` - validasi formula MOS/upside, bucket scoring (Quality/Valuation/Risk), verdict (BUY/HOLD/SELL), conservative IV blending.
- `tests/test_report.py` - validasi formatter (`fmt_pct`, `fmt_money`, ...), ASCII table renderer, layout output yang dilihat user.
- `tests/test_cli.py` - argparse, watchlist loader (cap 50, plain text vs CSV), TXT export round-trip ke tmp dir.

Test ini **murni offline** (tidak hit network) - safe dijalankan di CI / tanpa internet.

---

## 8. FAQ

**Q: Kenapa beberapa metrik N/A?**
A: yfinance tidak konsisten menyediakan semua field untuk semua emiten IDX. Saham kecil/jarang ditradingkan sering minim data. Bank besar (BBCA, BBRI, BMRI) biasanya datanya paling lengkap.

**Q: Data PER/PBV di dashboard beda dengan Stockbit, kenapa?**
A: yfinance pakai trailing 12-month dari laporan tahunan terakhir, sementara Stockbit sering pakai laporan kuartalan terbaru (LTM). Selisih 5-15% wajar. Untuk valuasi serius, cross-check ke laporan keuangan resmi IDX.

**Q: Cache disimpan di mana?**
A: `data/cache/` dalam bentuk JSON (untuk info) dan Parquet (untuk dataframe). TTL default 6 jam. Bisa di-clear dari sidebar atau hapus folder manual.

**Q: Saham bank — bagaimana NIM, LDR, CAR, BOPO dapat?**
A: Tidak ada di yfinance. Anda perlu (a) parse laporan triwulanan dari IDX (idx.co.id/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan), (b) langganan API Sectors.id, atau (c) scraping Stockbit. Kalau mau, saya bisa tambahkan modul `analyzer/bank_metrics.py` yang scraping IDX PDF/XBRL.

**Q: Bisa otomatis daily?**
A: Bisa. Pakai Windows Task Scheduler untuk jalankan script Python harian, atau pakai `schedule` library. Saya bisa tambahkan `cron.py` kalau perlu.

**Q: Aman secara legal?**
A: yfinance scraping public Yahoo data — untuk pemakaian pribadi/edukasi umumnya OK. Jangan dipakai komersial / re-distribute data tanpa izin Yahoo.

---

## 9. Roadmap (Saran Pengembangan)

- [ ] Modul khusus saham bank (NPL, NIM, CAR, BOPO via scraping IDX XBRL)
- [ ] Export Excel report multi-sheet (1 sheet per emiten)
- [ ] Notifikasi Telegram bot untuk MOS > threshold
- [ ] Backtest historis (jika beli saat MOS > 30%, return berapa?)
- [ ] Tambah sumber data Sectors.id (akurat untuk IDX)
- [ ] Sektor benchmark (bandingkan rasio emiten vs median sektornya)

---

## 10. Disclaimer

Aplikasi ini **bukan rekomendasi investasi**. Data Yahoo Finance bisa salah, delay, atau tidak lengkap. Selalu cross-check ke laporan keuangan resmi sebelum mengambil keputusan investasi. Penulis tidak bertanggung jawab atas kerugian akibat penggunaan tool ini.

---

## 11. Lisensi

MIT — bebas dipakai dan dimodifikasi. Kalau berguna, kasih bintang ke repo Anda sendiri ;)
