"""Export laporan ke TXT dan PDF.

- TXT: text rapi dengan summary table di atas, lalu detail-rows tabel per emiten.
- PDF: pakai ``reportlab`` (Platypus) untuk tabel asli (bukan render text).

PDF dibuat opsional: kalau reportlab tidak ter-install, ``export_pdf`` akan
raise ``ImportError`` dengan instruksi install.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from analyzer.report import (
    DISCLAIMER_TEXT,
    DcfAssumptions,
    SUMMARY_HEADERS,
    build_detail_rows,
    build_summary_rows,
    render_ascii_table,
    render_stock_section,
)
from analyzer.scoring import ScoreCard


# ----------------------------- TXT export -----------------------------

def export_txt(
    items: list[tuple[dict, ScoreCard]],
    dcf: DcfAssumptions,
    output_path: str | Path,
) -> Path:
    """Tulis laporan TXT (summary table + detail per emiten + disclaimer)."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    parts.append("=" * 72)
    parts.append("IDX FUNDAMENTAL ANALYZER - REPORT")
    parts.append(f"Generated   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(f"Stocks      : {len(items)}")
    parts.append("=" * 72)
    parts.append("")

    parts.append("RINGKASAN")
    parts.append("-" * 72)
    rows = build_summary_rows(items)
    parts.append(render_ascii_table(SUMMARY_HEADERS, rows))
    parts.append("")

    parts.append("DETAIL PER EMITEN")
    parts.append("-" * 72)
    for metrics, sc in items:
        parts.append(render_stock_section(metrics, sc, dcf))
        parts.append("")

        # Tabel detail kategori (Group | Metric | Value) supaya semua data
        # terangkum dalam tabel - sesuai permintaan user.
        detail_headers = ["Group", "Metric", "Value"]
        detail_rows = [list(r) for r in build_detail_rows(metrics, sc, dcf)]
        parts.append(render_ascii_table(detail_headers, detail_rows))
        parts.append("")

    parts.append("-" * 72)
    parts.append(DISCLAIMER_TEXT)

    out.write_text("\n".join(parts), encoding="utf-8")
    return out


# ----------------------------- PDF export -----------------------------

def export_pdf(
    items: list[tuple[dict, ScoreCard]],
    dcf: DcfAssumptions,
    output_path: str | Path,
) -> Path:
    """Tulis laporan PDF dengan tabel summary + tabel detail per emiten."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )
    except ImportError as e:
        raise ImportError(
            "reportlab belum ter-install. Jalankan:  "
            "pip install reportlab>=4.0.0"
        ) from e

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out),
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="IDX Fundamental Analyzer Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        alignment=0,
        fontSize=18,
        spaceAfter=8,
    )
    h2_style = ParagraphStyle(
        "H2Custom",
        parent=styles["Heading2"],
        fontSize=13,
        spaceAfter=6,
        spaceBefore=10,
    )
    h3_style = ParagraphStyle(
        "H3Custom",
        parent=styles["Heading3"],
        fontSize=11,
        spaceAfter=4,
        spaceBefore=8,
    )
    body_style = ParagraphStyle(
        "BodyCustom",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["BodyText"],
        fontSize=8,
        textColor=colors.grey,
        leading=10,
    )

    elements: list = []

    elements.append(Paragraph("IDX Fundamental Analyzer - Report", title_style))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;&nbsp; "
        f"Stocks: {len(items)} &nbsp;&nbsp; "
        f"DCF assumptions: WACC {dcf.discount * 100:.1f}%, "
        f"Growth {dcf.growth * 100:.1f}%, Terminal {dcf.terminal * 100:.1f}%",
        body_style,
    ))
    elements.append(Spacer(1, 8))

    # ----- Summary table -----
    elements.append(Paragraph("Ringkasan", h2_style))
    rows = build_summary_rows(items)
    summary_data = [SUMMARY_HEADERS] + rows
    summary_table = Table(summary_data, repeatRows=1, hAlign="LEFT")
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (-1, 1), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    # Warna verdict
    for i, row in enumerate(rows, start=1):
        verdict = row[-1]
        color = _verdict_color(verdict)
        if color is not None:
            summary_table.setStyle(TableStyle([
                ("BACKGROUND", (-1, i), (-1, i), color),
                ("TEXTCOLOR", (-1, i), (-1, i), colors.white),
                ("FONTNAME", (-1, i), (-1, i), "Helvetica-Bold"),
            ]))
    elements.append(summary_table)
    elements.append(PageBreak())

    # ----- Detail per emiten -----
    for idx, (metrics, sc) in enumerate(items):
        ticker = metrics.get("ticker") or "N/A"
        name = metrics.get("name") or ""
        elements.append(Paragraph(f"{ticker} - {name}", h2_style))

        sub = " | ".join(p for p in (metrics.get("sector"), metrics.get("industry")) if p)
        if sub:
            elements.append(Paragraph(sub, body_style))

        verdict_color = _verdict_color(sc.verdict) or colors.grey
        elements.append(Paragraph(
            f"<b>Verdict: <font color='{verdict_color.hexval()}'>{sc.verdict}</font></b> "
            f"&nbsp;&nbsp; Composite: {sc.composite if sc.composite is not None else 'N/A'} "
            f"&nbsp;&nbsp; MOS: {_pct_or_na(sc.mos)} "
            f"&nbsp;&nbsp; Upside: {_pct_or_na(sc.upside)}",
            body_style,
        ))
        elements.append(Spacer(1, 4))

        detail_rows = [list(r) for r in build_detail_rows(metrics, sc, dcf)]
        # Group rows berdasarkan kolom Group, lalu render satu tabel kolom 3.
        detail_data = [["Group", "Metric", "Value"]] + detail_rows
        detail_table = Table(detail_data, repeatRows=1, colWidths=[100, 180, 180], hAlign="LEFT")
        detail_table.setStyle(_detail_table_style(detail_rows))
        elements.append(detail_table)

        if idx < len(items) - 1:
            elements.append(PageBreak())

    elements.append(Spacer(1, 12))
    elements.append(Paragraph(DISCLAIMER_TEXT, footer_style))

    doc.build(elements)
    return out


def _detail_table_style(rows: list[list[str]]):
    """Style untuk tabel detail per emiten + alternating group colors."""
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    base = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    # Alternating row by group
    palette = [colors.whitesmoke, colors.white]
    last_group = None
    palette_idx = -1
    for i, row in enumerate(rows, start=1):
        group = row[0]
        if group != last_group:
            palette_idx = (palette_idx + 1) % len(palette)
            last_group = group
        base.append(("BACKGROUND", (0, i), (-1, i), palette[palette_idx]))

    return TableStyle(base)


def _verdict_color(verdict: str):
    """Map verdict ke warna reportlab."""
    from reportlab.lib import colors

    return {
        "BUY": colors.HexColor("#1b7a3e"),
        "ACCUMULATE": colors.HexColor("#2e8b57"),
        "HOLD": colors.HexColor("#7a7a7a"),
        "REDUCE": colors.HexColor("#c97a00"),
        "SELL": colors.HexColor("#a32020"),
    }.get(verdict)


def _pct_or_na(x: float | None) -> str:
    if x is None:
        return "N/A"
    return f"{x * 100:.2f}%"
