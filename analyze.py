"""IDX Fundamental Analyzer - CLI (full Python, no web UI).

Pemakaian dasar:

    # Pakai watchlist default (examples/watchlist.csv), max 50 emiten
    python analyze.py

    # Custom 1 atau lebih emiten (suffix .JK opsional, otomatis ditambahkan)
    python analyze.py --emiten BBRI.JK
    python analyze.py --emiten BBCA,BBRI,TLKM

    # Ganti file watchlist
    python analyze.py --watchlist examples/watchlist.csv

    # Export hasil
    python analyze.py --export txt
    python analyze.py --export pdf
    python analyze.py --export both --output-dir reports

    # Override asumsi DCF non-bank (semua dalam persen)
    python analyze.py --emiten ASII --wacc 11 --growth 7 --terminal 3.5

    # Override Cost of Equity untuk saham bank (DDM+PBV)
    python analyze.py --emiten BBCA --coe 11

Aturan:
- Watchlist maksimal 50 emiten. Jika file watchlist berisi >50, hanya 50
  pertama yang dianalisis (sesuai permintaan user).
- ``--emiten`` mem-bypass watchlist sepenuhnya.
- Output console selalu di-print. Export TXT/PDF opsional.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from analyzer.banking import is_banking_stock
from analyzer.fetcher import StockFetcher, normalize_ticker
from analyzer.metrics import compute_metrics
from analyzer.report import (
    DISCLAIMER_TEXT,
    DcfAssumptions,
    SUMMARY_HEADERS,
    build_summary_rows,
    render_ascii_table,
    render_stock_section,
)
from analyzer.scoring import build_scorecard
from analyzer.valuation import graham_number, simple_dcf

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WATCHLIST = PROJECT_ROOT / "examples" / "watchlist.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports"

WATCHLIST_LIMIT = 50  # batas keras sesuai permintaan


# ----------------------------- Argparse -----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="analyze",
        description="IDX Fundamental Analyzer - CLI fundamental & valuasi saham IDX.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--emiten",
        type=str,
        default=None,
        help="Satu atau lebih kode saham, dipisah koma. Contoh: BBRI.JK atau BBCA,BBRI,TLKM",
    )
    p.add_argument(
        "--watchlist",
        type=str,
        default=str(DEFAULT_WATCHLIST),
        help=f"Path ke file watchlist CSV (kolom 'ticker') atau plain text. Default: {DEFAULT_WATCHLIST}",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=WATCHLIST_LIMIT,
        help=f"Maksimum emiten yang diproses dari watchlist. Default & cap: {WATCHLIST_LIMIT}",
    )
    p.add_argument(
        "--export",
        choices=["txt", "pdf", "both", "none"],
        default="none",
        help="Format export hasil. Default: none (cuma print ke console)",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Folder output untuk export. Default: {DEFAULT_OUTPUT_DIR}",
    )
    p.add_argument(
        "--wacc",
        type=float,
        default=12.0,
        help="WACC / discount rate untuk DCF non-bank, persen. Default 12 (kalibrasi IDX).",
    )
    p.add_argument(
        "--coe",
        type=float,
        default=10.0,
        help="Cost of Equity untuk DDM+PBV saham bank, persen. Default 10.",
    )
    p.add_argument(
        "--growth",
        type=float,
        default=8.0,
        help="Growth FCF 10Y untuk DCF, persen. Default 8.",
    )
    p.add_argument(
        "--terminal",
        type=float,
        default=4.0,
        help="Terminal growth untuk DCF, persen. Default 4.",
    )
    p.add_argument(
        "--years",
        type=int,
        default=10,
        help="Horizon DCF dalam tahun. Default 10.",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache; selalu hit yfinance.",
    )
    p.add_argument(
        "--cache-hours",
        type=float,
        default=6.0,
        help="TTL cache dalam jam. Default 6.",
    )
    p.add_argument(
        "--no-summary",
        action="store_true",
        help="Jangan tampilkan summary table di console (cuma per-emiten section).",
    )
    return p


# ----------------------------- Loaders -----------------------------

def load_tickers(args: argparse.Namespace) -> list[str]:
    """Resolve daftar ticker dari ``--emiten`` atau file watchlist.

    Aturan watchlist: maksimum 50 (atau ``--limit`` lebih kecil).
    Jika file mengandung lebih banyak, sisanya di-skip dengan warning.
    """
    if args.emiten:
        raw_list = [t.strip() for t in args.emiten.split(",") if t.strip()]
        if not raw_list:
            raise SystemExit("Argumen --emiten kosong.")
        return [normalize_ticker(t) for t in raw_list]

    path = Path(args.watchlist)
    if not path.exists():
        raise SystemExit(
            f"Watchlist tidak ditemukan: {path}\n"
            "Berikan --watchlist <file> atau pakai --emiten."
        )

    raw_lines: list[str]
    if path.suffix.lower() == ".csv":
        # Parse CSV ringan tanpa pandas, ambil kolom 'ticker' jika ada,
        # kalau tidak pakai kolom pertama.
        import csv
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            raise SystemExit(f"Watchlist kosong: {path}")
        header = [c.strip().lower() for c in rows[0]]
        if "ticker" in header:
            idx = header.index("ticker")
            raw_lines = [r[idx] for r in rows[1:] if r and r[idx].strip()]
        else:
            # Tanpa header, anggap kolom pertama
            raw_lines = [r[0] for r in rows if r and r[0].strip()]
    else:
        raw_lines = [
            ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]

    cleaned = [t for t in (s.strip() for s in raw_lines) if t]
    cap = min(args.limit, WATCHLIST_LIMIT)
    if len(cleaned) > cap:
        print(
            f"[!] Watchlist berisi {len(cleaned)} emiten, dibatasi ke {cap} (cap = {WATCHLIST_LIMIT}).",
            file=sys.stderr,
        )
        cleaned = cleaned[:cap]
    return [normalize_ticker(t) for t in cleaned]


# ----------------------------- Pipeline -----------------------------

def analyze_tickers(
    tickers: list[str],
    fetcher: StockFetcher,
    dcf: DcfAssumptions,
    years: int,
    cost_of_equity: float,
) -> list[tuple[dict, "object"]]:
    """Fetch + compute metrics + scorecard untuk semua ticker.

    Saham bank (sector/industry mengandung kata kunci ``bank``) otomatis
    skip Graham/DCF dan pakai DDM + Justified PBV (lihat ``analyzer.banking``).
    Saat fetch satu emiten gagal, log error dan lanjut ke yang lain (resilient).
    """
    results: list[tuple[dict, object]] = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, start=1):
        print(f"[{i}/{total}] Mengambil {ticker} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            data = fetcher.fetch(ticker)
            metrics = compute_metrics(data)
        except Exception as e:
            print(f"GAGAL ({type(e).__name__}: {e})")
            continue

        if not metrics.get("name") and not metrics.get("current_price"):
            print("DATA KOSONG (skipped)")
            continue

        # Untuk bank, Graham + DCF berbasis FCF mis-leading -> skip.
        if is_banking_stock(metrics):
            graham = None
            dcf_value = None
            tag = "[BANK]"
        else:
            graham = graham_number(
                metrics.get("eps"), metrics.get("book_value_per_share")
            )
            dcf_value = simple_dcf(
                free_cash_flow=metrics.get("free_cash_flow"),
                shares_outstanding=metrics.get("shares_outstanding"),
                growth_rate=dcf.growth,
                terminal_growth=dcf.terminal,
                discount_rate=dcf.discount,
                years=years,
                cash=_extract_cash(metrics),
                debt=metrics.get("total_debt") or 0.0,
            )
            tag = ""

        sc = build_scorecard(
            metrics, graham, dcf_value, cost_of_equity=cost_of_equity
        )
        results.append((metrics, sc))
        suffix = f" {tag}" if tag else ""
        print(f"OK ({time.time() - t0:.1f}s) - {sc.verdict}{suffix}")

    return results


def _extract_cash(metrics: dict) -> float:
    """Cash = total_debt - net_debt jika keduanya ada, else 0.

    Logika sama dengan ``analyzer.valuation.intrinsic_value_summary``.
    """
    td = metrics.get("total_debt")
    nd = metrics.get("net_debt")
    if td is None or nd is None:
        return 0.0
    try:
        return float(td) - float(nd)
    except (TypeError, ValueError):
        return 0.0


# ----------------------------- Console output -----------------------------

def print_results(results: list[tuple[dict, "object"]], dcf: DcfAssumptions, show_summary: bool) -> None:
    if not results:
        print("\n(Tidak ada hasil yang bisa ditampilkan.)")
        return

    print()
    if show_summary and len(results) > 1:
        print("=" * 72)
        print(f"RINGKASAN ({len(results)} emiten)")
        print("=" * 72)
        print(render_ascii_table(SUMMARY_HEADERS, build_summary_rows(results)))
        print()

    print("=" * 72)
    print("DETAIL")
    print("=" * 72)
    for metrics, sc in results:
        print(render_stock_section(metrics, sc, dcf))
    print("-" * 72)
    print(DISCLAIMER_TEXT)


# ----------------------------- Export wrapper -----------------------------

def maybe_export(
    results: list[tuple[dict, object]],
    args: argparse.Namespace,
    dcf: DcfAssumptions,
) -> None:
    if args.export == "none" or not results:
        return

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")

    if args.emiten:
        slug = args.emiten.replace(",", "_").replace(".", "_").upper()
        base = f"idx_report_{slug}_{stamp}"
    else:
        base = f"idx_report_{stamp}"

    if args.export in ("txt", "both"):
        from analyzer.export import export_txt
        path = export_txt(results, dcf, out_dir / f"{base}.txt")
        print(f"[OK] TXT  -> {path}")

    if args.export in ("pdf", "both"):
        try:
            from analyzer.export import export_pdf
            path = export_pdf(results, dcf, out_dir / f"{base}.pdf")
            print(f"[OK] PDF  -> {path}")
        except ImportError as e:
            print(f"[!] PDF skip: {e}", file=sys.stderr)


# ----------------------------- Main -----------------------------

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    dcf = DcfAssumptions(
        growth=args.growth / 100,
        terminal=args.terminal / 100,
        discount=args.wacc / 100,
    )
    if dcf.discount <= dcf.terminal:
        print(
            f"[!] WACC ({args.wacc}%) harus > Terminal Growth ({args.terminal}%). "
            "Periksa --wacc / --terminal.",
            file=sys.stderr,
        )
        return 2

    tickers = load_tickers(args)
    if not tickers:
        print("Tidak ada ticker untuk diproses.", file=sys.stderr)
        return 1

    print(f"Menganalisis {len(tickers)} emiten:")
    print("  " + ", ".join(tickers))
    print(
        f"DCF (non-bank): WACC {args.wacc}%, Growth {args.growth}%, "
        f"Terminal {args.terminal}%, Years {args.years}"
    )
    print(
        f"Banking model : DDM 50% + Justified PBV 50%, Cost of Equity {args.coe}%"
    )
    print()

    fetcher = StockFetcher(
        cache_ttl=int(args.cache_hours * 3600),
        use_cache=not args.no_cache,
    )
    results = analyze_tickers(
        tickers,
        fetcher,
        dcf,
        years=args.years,
        cost_of_equity=args.coe / 100,
    )

    print_results(results, dcf, show_summary=not args.no_summary)
    maybe_export(results, args, dcf)

    if not results:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
