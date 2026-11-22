"""PDF export — generates a white-label PDF report from ui_config.json.

Shared module used by both the Streamlit sidebar button and the MCP tool.
Builds an HTML report with WeasyPrint-friendly styling, exports Plotly charts
to PNG via Kaleido, and converts the whole document to PDF.

Dependencies:
    - weasyprint (HTML → PDF)
    - kaleido (Plotly → PNG, already installed)
"""
from __future__ import annotations

import base64
import io
import logging
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from .data import has_data
from .tools import execute_kpi, execute_query

_logger = logging.getLogger("pdf_export")

# --------------------------------------------------------------------------- #
# Chart building — mirrors components.py render_chart logic without Streamlit
# --------------------------------------------------------------------------- #

_PALETTE = [
    "#246bfd", "#f59f00", "#10b981", "#ef4444",
    "#8b5cf6", "#ec4899", "#06b6d4", "#f97316",
]


def _is_hex_color(value: Any) -> bool:
    return isinstance(value, str) and re.match(r"^#[0-9a-fA-F]{3,8}$", value) is not None


def _build_chart_figure(chart_config: dict, df: pd.DataFrame):
    """Build a Plotly figure from a chart config dict (no Streamlit rendering).

    Returns a plotly Figure object or None if the chart cannot be built.
    """
    if df.empty:
        return None

    try:
        import plotly.express as px
    except ImportError:
        _logger.warning("plotly not installed; skipping chart")
        return None

    tipo = chart_config.get("tipo", "bar")
    alto = chart_config.get("alto", 350)

    def _style(fig):
        fig.update_layout(
            height=alto,
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(family="-apple-system, Segoe UI, Roboto, sans-serif", color="#334155", size=12),
            margin=dict(l=40, r=20, t=30, b=50),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10), showgrid=False, linecolor="#e2e8f0"),
            yaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False),
        )
        return fig

    if tipo == "bar":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return None
        if _is_hex_color(color_raw):
            fig = px.bar(df, x=x, y=y, color_discrete_sequence=[color_raw])
        else:
            fig = px.bar(df, x=x, y=y, color=color_raw, color_discrete_sequence=_PALETTE)
        fig = _style(fig)
        return fig

    elif tipo == "bar_h":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return None
        if _is_hex_color(color_raw):
            fig = px.bar(df, x=x, y=y, orientation="h", color_discrete_sequence=[color_raw])
        elif color_raw:
            fig = px.bar(df, x=x, y=y, orientation="h", color=color_raw, color_discrete_sequence=_PALETTE)
        else:
            fig = px.bar(df, x=x, y=y, orientation="h", color_discrete_sequence=_PALETTE)
        fig = _style(fig)
        fig.update_layout(yaxis=dict(title=""))
        return fig

    elif tipo == "pie":
        columna = chart_config.get("columna")
        valores = chart_config.get("valores")
        if not columna or not valores:
            return None
        fig = px.pie(df, names=columna, values=valores, hole=0.58, color_discrete_sequence=_PALETTE)
        fig.update_traces(textinfo="percent", textposition="inside", textfont=dict(color="white", size=11))
        fig = _style(fig)
        return fig

    elif tipo == "line":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return None
        if _is_hex_color(color_raw):
            fig = px.line(df, x=x, y=y, color_discrete_sequence=[color_raw])
        else:
            fig = px.line(df, x=x, y=y, color=color_raw, color_discrete_sequence=_PALETTE)
        fig = _style(fig)
        return fig

    elif tipo == "scatter":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        size = chart_config.get("size")
        if not x or not y:
            return None
        if _is_hex_color(color_raw):
            fig = px.scatter(df, x=x, y=y, size=size, color_discrete_sequence=[color_raw], opacity=0.8)
        else:
            fig = px.scatter(df, x=x, y=y, color=color_raw, size=size, color_discrete_sequence=_PALETTE, opacity=0.8)
        fig = _style(fig)
        return fig

    elif tipo == "heatmap":
        x = chart_config.get("x")
        y = chart_config.get("y")
        valores = chart_config.get("valores")
        if not x or not y or not valores:
            return None
        cruz = pd.pivot_table(df, index=y, columns=x, values=valores, aggfunc="sum").fillna(0)
        fig = px.imshow(cruz, text_auto=True, aspect="auto", color_continuous_scale=["#e0f2fe", "#246bfd"])
        fig.update_layout(height=alto, margin=dict(l=40, r=20, t=30, b=40), paper_bgcolor="white",
                          font=dict(color="#334155", size=11))
        return fig

    elif tipo in ("bar_grouped", "bar_stacked"):
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return None
        barmode = "group" if tipo == "bar_grouped" else "stack"
        if _is_hex_color(color_raw):
            fig = px.bar(df, x=x, y=y, barmode=barmode, color_discrete_sequence=[color_raw])
        else:
            fig = px.bar(df, x=x, y=y, color=color_raw, barmode=barmode, color_discrete_sequence=_PALETTE)
        fig = _style(fig)
        return fig

    return None


def _chart_to_png_base64(chart_config: dict, df: pd.DataFrame) -> str | None:
    """Export a chart to a base64-encoded PNG string for embedding in HTML."""
    fig = _build_chart_figure(chart_config, df)
    if fig is None:
        return None
    try:
        img_bytes = fig.to_image(format="png", scale=2)
        return base64.b64encode(img_bytes).decode("ascii")
    except Exception as e:
        _logger.warning(f"Failed to export chart to PNG: {e}")
        return None


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def _format_kpi_value(value: Any, fmt: str) -> str:
    """Format a KPI value for display in the PDF."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "0"
    if fmt == "money":
        return f"${float(value):,.2f}"
    elif fmt == "int":
        return f"{int(value):,}"
    elif fmt == "percent":
        return f"{float(value):.1f}%"
    elif fmt == "str":
        return str(value)
    return str(value)


# --------------------------------------------------------------------------- #
# HTML template (embedded, no external files)
# --------------------------------------------------------------------------- #

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
  @page {
    size: A4;
    margin: 20mm;
    @bottom-center {
      content: "Página " counter(page) " de " counter(pages);
      font-size: 9px;
      color: #94a3b8;
    }
  }
  body {
    font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    color: #0f172a;
    margin: 0;
    padding: 0;
    line-height: 1.5;
  }
  .cover {
    page-break-after: always;
    text-align: center;
    padding-top: 80px;
  }
  .cover h1 {
    font-size: 28px;
    color: #0f172a;
    margin-bottom: 8px;
  }
  .cover .subtitle {
    font-size: 16px;
    color: #64748b;
    margin-bottom: 40px;
  }
  .cover .date {
    font-size: 12px;
    color: #94a3b8;
  }
  .section {
    page-break-inside: avoid;
    margin-bottom: 30px;
  }
  .section h2 {
    font-size: 18px;
    color: #0f172a;
    border-bottom: 2px solid #246bfd;
    padding-bottom: 6px;
    margin-bottom: 16px;
  }
  .kpi-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }
  .kpi-card {
    flex: 1;
    min-width: 140px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px;
    text-align: center;
  }
  .kpi-card .label {
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .kpi-card .value {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    margin: 4px 0;
  }
  .kpi-card .sub {
    font-size: 10px;
    color: #94a3b8;
  }
  .chart-img {
    width: 100%;
    max-height: 350px;
    object-fit: contain;
    margin: 10px 0;
  }
  .chart-title {
    font-size: 14px;
    font-weight: 600;
    color: #334155;
    margin-bottom: 4px;
  }
  .chart-subtitle {
    font-size: 11px;
    color: #94a3b8;
    margin-bottom: 8px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    margin: 10px 0;
  }
  th {
    background: #f1f5f9;
    color: #334155;
    font-weight: 600;
    text-align: left;
    padding: 8px 10px;
    border-bottom: 2px solid #e2e8f0;
  }
  td {
    padding: 6px 10px;
    border-bottom: 1px solid #f1f5f9;
    color: #475569;
  }
  .footer {
    text-align: center;
    font-size: 9px;
    color: #cbd5e1;
    margin-top: 30px;
    padding-top: 10px;
    border-top: 1px solid #f1f5f9;
  }
</style>
</head>
<body>

{cover}

{sections}

<div class="footer">{footer}</div>

</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def generate_pdf(config: dict, filter_values: dict | None = None) -> bytes:
    """Generate a PDF report from a ui_config.json dict.

    Args:
        config: The full ui_config.json dictionary.
        filter_values: Optional filter values to apply (same format as Streamlit).

    Returns:
        Raw PDF bytes ready to save or stream.
    """
    if not has_data():
        raise ValueError("No data available. Ingest a CSV first.")

    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError(
            "weasyprint is required for PDF export. "
            "Install it with: pip install weasyprint"
        )

    brand_name = config.get("brand_name", "Dashboard")
    brand_sub = config.get("brand_sub", "")
    footer_text = config.get("footer", "")
    filter_config = config.get("filtros_globales", [])
    modulos = config.get("modulos", [])

    # --- Cover page ---
    today = datetime.now().strftime("%d/%m/%Y")
    cover_html = f"""\
<div class="cover">
    <h1>{escape(brand_name)}</h1>
    {f'<div class="subtitle">{escape(brand_sub)}</div>' if brand_sub else ""}
    <div class="date">Reporte generado el {today}</div>
</div>
"""

    # --- Sections per module ---
    sections_html = ""

    for mod in modulos:
        mod_name = mod.get("nombre", "Módulo")
        sections_html += f'<div class="section"><h2>{escape(mod_name)}</h2>'

        # KPIs
        kpis = mod.get("kpis", [])
        if kpis:
            kpi_cards = ""
            for kpi_cfg in kpis:
                val = execute_kpi(kpi_cfg, filter_config, filter_values)
                formatted = _format_kpi_value(val, kpi_cfg.get("formato", "number"))
                label = kpi_cfg.get("label", "")
                sub_label = kpi_cfg.get("sub_label", "")
                kpi_cards += f"""\
<div class="kpi-card">
    <div class="label">{escape(label)}</div>
    <div class="value">{escape(formatted)}</div>
    {f'<div class="sub">{escape(sub_label)}</div>' if sub_label else ""}
</div>
"""
            sections_html += f'<div class="kpi-row">{kpi_cards}</div>'

        # Charts
        charts = mod.get("graficos", [])
        for chart_cfg in charts:
            title = chart_cfg.get("titulo", "Gráfico")
            subtitle = chart_cfg.get("sub", "")

            # Execute query
            df = execute_query(chart_cfg, filter_config, filter_values)
            if df.empty:
                sections_html += f'<div class="chart-title">{escape(title)}</div><p style="color:#94a3b8;font-size:11px;">Sin datos</p>'
                continue

            # Apply renames
            rename = chart_cfg.get("rename", {})
            if rename:
                df = df.rename(columns=rename)

            # Apply top_n
            top_n = chart_cfg.get("top_n")
            if top_n and "x" in chart_cfg:
                x_col = chart_cfg["x"]
                if x_col in df.columns:
                    top_values = df[x_col].value_counts().head(top_n).index.tolist()
                    df = df[df[x_col].isin(top_values)]

            # Build chart config for _build_chart_figure
            chart_build_cfg = {
                "tipo": chart_cfg.get("tipo", "bar"),
                "alto": chart_cfg.get("alto", 350),
            }
            for key in ("x", "y", "columna", "valores", "color", "size"):
                if key in chart_cfg:
                    chart_build_cfg[key] = chart_cfg[key]

            png_b64 = _chart_to_png_base64(chart_build_cfg, df)
            if png_b64:
                sections_html += f"""\
<div class="chart-title">{escape(title)}</div>
{f'<div class="chart-subtitle">{escape(subtitle)}</div>' if subtitle else ""}
<img class="chart-img" src="data:image/png;base64,{png_b64}" alt="{escape(title)}">
"""
            else:
                sections_html += f'<div class="chart-title">{escape(title)}</div><p style="color:#94a3b8;font-size:11px;">Gráfico no disponible</p>'

        # Tables
        tables = mod.get("tablas", [])
        for table_cfg in tables:
            t_title = table_cfg.get("titulo", "Tabla")
            sections_html += f'<div class="chart-title">{escape(t_title)}</div>'
            df = execute_query(table_cfg, filter_config, filter_values)
            limit = table_cfg.get("limite", 50)
            if not df.empty:
                df_display = df.head(limit)
                # Convert DataFrame to HTML table
                table_html = df_display.to_html(escape=True, index=False, border=0)
                sections_html += table_html
            else:
                sections_html += '<p style="color:#94a3b8;font-size:11px;">Sin datos</p>'

        sections_html += '</div>'  # .section

    # --- Assemble full HTML ---
    full_html = HTML_TEMPLATE.format(
        cover=cover_html,
        sections=sections_html,
        footer=escape(footer_text) if footer_text else "",
    )

    # --- Convert to PDF ---
    pdf_bytes = HTML(string=full_html).write_pdf()
    return pdf_bytes


def generate_pdf_to_file(config: dict, output_path: str | Path, filter_values: dict | None = None) -> Path:
    """Generate a PDF report and save it to a file.

    Args:
        config: The full ui_config.json dictionary.
        output_path: Where to save the PDF.
        filter_values: Optional filter values.

    Returns:
        The Path object of the saved file.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = generate_pdf(config, filter_values)
    output.write_bytes(pdf_bytes)
    _logger.info(f"PDF saved to {output} ({len(pdf_bytes)} bytes)")
    return output
