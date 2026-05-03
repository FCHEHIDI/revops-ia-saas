"""PDF rendering helpers for RevOps IA report generation.

Provides low-level FPDF drawing primitives and the high-level ``render_pdf``
entry point.  Extracted from ``reports/service.py`` to respect SRP.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fpdf import FPDF

from app.common.utils import utcnow


# ---------------------------------------------------------------------------
# Low-level drawing primitives
# ---------------------------------------------------------------------------


def _section_header(pdf: FPDF, title: str) -> None:
    """Render a blue section header with an underline.

    Args:
        pdf: Active FPDF instance.
        title: Section title text.
    """
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 64, 175)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(30, 64, 175)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(0, 0, 0)


def _kv_row(pdf: FPDF, key: str, value: str) -> None:
    """Render a key-value row.

    Args:
        pdf: Active FPDF instance.
        key: Label text.
        value: Value text.
    """
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(75, 7, f"{key}:", new_x="RIGHT", new_y="LAST")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")


def _table_header(pdf: FPDF, cols: list[str], widths: list[int]) -> None:
    """Render a shaded table header row.

    Args:
        pdf: Active FPDF instance.
        cols: Column label strings.
        widths: Column widths in mm.
    """
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(220, 228, 255)
    for col, w in zip(cols, widths):
        pdf.cell(w, 8, col, border=1, fill=True)
    pdf.ln()


def _table_row(pdf: FPDF, cells: list[str], widths: list[int]) -> None:
    """Render a single data row.

    Args:
        pdf: Active FPDF instance.
        cells: Cell content strings.
        widths: Column widths in mm.
    """
    pdf.set_font("Helvetica", "", 9)
    pdf.set_fill_color(255, 255, 255)
    for cell, w in zip(cells, widths):
        pdf.cell(w, 7, cell, border=1)
    pdf.ln()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_pdf(
    report_type: str,
    data: dict[str, Any],
    tenant_id: UUID,
) -> bytes:
    """Render a PDF report from aggregated data.

    Args:
        report_type: One of pipeline | mrr | team_performance | churn.
        data: Aggregated data dict from the corresponding fetcher.
        tenant_id: Owning tenant UUID (shown in PDF footer).

    Returns:
        Raw PDF bytes.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(10, 10, 10)

    _TITLES = {
        "pipeline": "Pipeline Report",
        "mrr": "MRR Report",
        "team_performance": "Team Performance Report",
        "churn": "Churn Analysis Report",
    }
    title = _TITLES.get(report_type, "Report")

    # ── Title bar ──────────────────────────────────────────────────────────
    pdf.set_fill_color(30, 64, 175)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_xy(0, 7)
    pdf.cell(210, 12, title, align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Metadata line ─────────────────────────────────────────────────────
    pdf.set_text_color(120, 120, 120)
    pdf.set_font("Helvetica", "", 8)
    generated = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    pdf.set_xy(10, 32)
    pdf.cell(
        0,
        6,
        f"Generated: {generated}   |   Tenant: {tenant_id}",
    )
    pdf.ln(12)
    pdf.set_text_color(0, 0, 0)

    # ── Report-specific content ───────────────────────────────────────────
    if report_type == "pipeline":
        _section_header(pdf, "Pipeline Summary")
        _kv_row(pdf, "Total Deals", str(data["total_deals"]))
        _kv_row(pdf, "Total Pipeline Value", f"EUR {data['total_value']:,.2f}")
        _kv_row(pdf, "Win Rate", f"{data['win_rate']}%")
        pdf.ln(4)
        _section_header(pdf, "Deals by Stage")
        _table_header(pdf, ["Stage", "Count", "Value (EUR)"], [80, 30, 70])
        for row in data["stages"]:
            _table_row(
                pdf,
                [row["stage"], str(row["count"]), f"{row['total']:,.2f}"],
                [80, 30, 70],
            )

    elif report_type == "mrr":
        _section_header(pdf, "MRR Summary")
        _kv_row(pdf, "Total ARR (top 20)", f"EUR {data['total_arr']:,.2f}")
        pdf.ln(4)
        _section_header(pdf, "Top Accounts by ARR")
        _table_header(
            pdf, ["Account", "Status", "Industry", "ARR (EUR)"], [60, 25, 50, 45]
        )
        for acc in data["accounts"]:
            _table_row(
                pdf,
                [
                    acc["name"][:28],
                    acc["status"],
                    (acc["industry"] or "N/A")[:20],
                    f"{acc['arr']:,.2f}",
                ],
                [60, 25, 50, 45],
            )

    elif report_type == "team_performance":
        _section_header(pdf, "Team Performance Summary")
        _kv_row(pdf, "Active Reps", str(data["total_reps"]))
        pdf.ln(4)
        _section_header(pdf, "Deals by Sales Rep")
        _table_header(
            pdf, ["Owner ID", "Deals", "Won", "Value (EUR)"], [80, 25, 25, 50]
        )
        for rep in data["reps"]:
            _table_row(
                pdf,
                [
                    rep["owner_id"][:20],
                    str(rep["deal_count"]),
                    str(rep["won_count"]),
                    f"{rep['total_value']:,.2f}",
                ],
                [80, 25, 25, 50],
            )

    elif report_type == "churn":
        _section_header(pdf, "Churn Analysis Summary")
        _kv_row(pdf, "Total Accounts", str(data["total_accounts"]))
        _kv_row(pdf, "Churned", str(data["churned"]))
        _kv_row(pdf, "Churn Rate", f"{data['churn_rate']}%")
        _kv_row(pdf, "Total Contacts", str(data["total_contacts"]))
        pdf.ln(4)
        _section_header(pdf, "Accounts by Status")
        _table_header(pdf, ["Status", "Count"], [100, 40])
        for row in data["by_status"]:
            _table_row(pdf, [row["status"], str(row["count"])], [100, 40])

    return bytes(pdf.output())
