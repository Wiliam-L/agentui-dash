"""PDF export — generates a white-label PDF report from ui_config.json.

Shared module used by both the Streamlit sidebar button and the MCP tool.
Builds a PDF directly with FPDF2, exports Plotly charts to PNG via Kaleido,
and embeds them as images. No system dependencies required — works on any OS.

Dependencies:
    - fpdf2 (pure Python PDF generation)
    - kaleido (Plotly → PNG, already installed)
"""
from __future__ import annotations

import io
import logging
import math
import re
from datetime import datetime
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


def _chart_to_png(chart_config: dict, df: pd.DataFrame) -> bytes | None:
    """Export a chart to PNG bytes for embedding in the PDF."""
    fig = _build_chart_figure(chart_config, df)
    if fig is None:
        return None
    try:
        img_bytes = fig.to_image(format="png", scale=2)
        return img_bytes
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
# FPDF helpers
# --------------------------------------------------------------------------- #

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string to an RGB tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _draw_rounded_rect(pdf, x, y, w, h, r, style="F"):
    """Draw a rounded rectangle using FPDF polygon."""
    k = pdf.k
    x_pt, y_pt = x * k, y * k
    w_pt, h_pt = w * k, h * k
    r_pt = r * k
    
    # Define rounded rectangle path
    pdf._out(f"q {x_pt} {y_pt} m")
    pdf._out(f"{x_pt + w_pt - r_pt} {y_pt} l")
    pdf._out(f"{x_pt + w_pt - r_pt} {y_pt} {x_pt + w_pt} {y_pt} {x_pt + w_pt} {y_pt + r_pt} c")
    pdf._out(f"{x_pt + w_pt} {y_pt + h_pt - r_pt} l")
    pdf._out(f"{x_pt + w_pt} {y_pt + h_pt - r_pt} {x_pt + w_pt} {y_pt + h_pt} {x_pt + w_pt - r_pt} {y_pt + h_pt} c")
    pdf._out(f"{x_pt + r_pt} {y_pt + h_pt} l")
    pdf._out(f"{x_pt + r_pt} {y_pt + h_pt} {x_pt} {y_pt + h_pt} {x_pt} {y_pt + h_pt - r_pt} c")
    pdf._out(f"{x_pt} {y_pt + r_pt} l")
    pdf._out(f"{x_pt} {y_pt + r_pt} {x_pt} {y_pt} {x_pt + r_pt} {y_pt} c")
    
    if style in ("F", "DF"):
        pdf._out("f")
    if style in ("D", "DF"):
        pdf._out("S")
    pdf._out("Q")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def generate_pdf(config: dict, filter_values: dict | None = None) -> bytes:
    """Generate a PDF report from a ui_config.json dict using FPDF2.

    Args:
        config: The full ui_config.json dictionary.
        filter_values: Optional filter values to apply (same format as Streamlit).

    Returns:
        Raw PDF bytes ready to save or stream.
    """
    if not has_data():
        raise ValueError("No data available. Ingest a CSV first.")

    try:
        from fpdf import FPDF
    except ImportError:
        raise ImportError(
            "fpdf2 is required for PDF export. "
            "Install it with: pip install fpdf2"
        )

    brand_name = config.get("brand_name", "Dashboard")
    brand_sub = config.get("brand_sub", "")
    footer_text = config.get("footer", "")
    filter_config = config.get("filtros_globales", [])
    modulos = config.get("modulos", [])
    primary_color = config.get("primary_color", "#246bfd")
    report_title = config.get("report_title", brand_name)

    # Parse primary color
    try:
        primary_rgb = _hex_to_rgb(primary_color) if primary_color else (36, 107, 253)
    except (ValueError, TypeError):
        primary_rgb = (36, 107, 253)
    
    # Lighter shade for accents
    light_primary = tuple(min(255, int(c * 0.1) + 240) for c in primary_rgb)
    # Medium shade for backgrounds
    medium_primary = tuple(min(255, int(c * 0.2) + 200) for c in primary_rgb)

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=25)

    # Use built-in fonts (Helvetica, Times, Courier) available on any OS
    # For Unicode support (Spanish accents), try to add a system font
    _font_added = False
    _font_family = "Helvetica"
    _font_paths = [
        # Windows
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf",
         r"C:\Windows\Fonts\ariali.ttf", r"C:\Windows\Fonts\arialbi.ttf"),
        # macOS
        ("/System/Library/Fonts/Helvetica.ttc", None, None, None),
        # Linux
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
    ]
    for regular, bold, italic, bolditalic in _font_paths:
        if regular and Path(regular).exists():
            try:
                pdf.add_font("Arial", "", regular, uni=True)
                if bold and Path(bold).exists():
                    pdf.add_font("Arial", "B", bold, uni=True)
                if italic and Path(italic).exists():
                    pdf.add_font("Arial", "I", italic, uni=True)
                if bolditalic and Path(bolditalic).exists():
                    pdf.add_font("Arial", "BI", bolditalic, uni=True)
                _font_family = "Arial"
                _font_added = True
                break
            except Exception:
                continue

    pdf.set_font(_font_family, size=12)

    # Store references for header/footer callbacks
    pdf._primary_rgb = primary_rgb
    pdf._medium_primary = medium_primary
    pdf._font_family = _font_family
    pdf._footer_text = footer_text
    pdf._current_module = ""

    def _custom_header(pdf):
        """Custom header called automatically by FPDF."""
        if pdf.page_no() == 1:
            return  # Skip header on cover page
        if pdf._current_module:
            _draw_header(pdf, pdf._current_module)
            pdf.ln(8)

    def _custom_footer(pdf):
        """Custom footer called automatically by FPDF."""
        if pdf.page_no() == 1:
            return  # Skip footer on cover page
        pdf.set_y(-20)
        # Line separator
        pdf.set_draw_color(226, 232, 240)
        pdf.set_line_width(0.2)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(1)
        # Footer text
        pdf.set_font(pdf._font_family, size=7)
        pdf.set_text_color(148, 163, 184)
        if pdf._footer_text:
            pdf.cell(95, 5, pdf._footer_text, align="L")
        pdf.cell(95, 5, f"Página {pdf.page_no()}", align="R")

    pdf.header = lambda: _custom_header(pdf)
    pdf.footer = lambda: _custom_footer(pdf)

    # Store module info for TOC
    module_info = []

    def _draw_header(pdf, title: str):
        """Draw professional header with gradient-like effect."""
        # Main header bar
        pdf.set_fill_color(*primary_rgb)
        pdf.rect(0, 0, 210, 15, "F")
        
        # Accent line at bottom
        pdf.set_fill_color(*medium_primary)
        pdf.rect(0, 15, 210, 1, "F")
        
        # Title text
        pdf.set_y(4)
        pdf.set_x(15)
        pdf.set_font(_font_family, "B", size=12)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 7, title, align="L")
        
        # Page indicator
        pdf.set_x(195)
        pdf.set_font(_font_family, size=8)
        pdf.cell(0, 7, str(pdf.page_no()), align="R")

    # --- Cover page ---
    pdf.add_page()
    
    # Top color bar
    pdf.set_fill_color(*primary_rgb)
    pdf.rect(0, 0, 210, 80, "F")
    
    # Accent line
    pdf.set_fill_color(*medium_primary)
    pdf.rect(0, 80, 210, 3, "F")
    
    # Brand name
    pdf.set_y(30)
    pdf.set_font(_font_family, "B", size=28)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 14, brand_name, align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Subtitle
    if brand_sub:
        pdf.set_font(_font_family, size=14)
        pdf.set_text_color(240, 240, 250)
        pdf.cell(0, 10, brand_sub, align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Date and info
    pdf.set_y(100)
    pdf.set_font(_font_family, "B", size=16)
    pdf.set_text_color(*primary_rgb)
    pdf.cell(0, 10, report_title, align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(5)
    pdf.set_font(_font_family, size=10)
    pdf.set_text_color(100, 116, 139)
    today = datetime.now().strftime("%d de %B de %Y")
    pdf.cell(0, 8, f"Generado el {today}", align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Table of contents
    pdf.ln(15)
    pdf.set_font(_font_family, "B", size=12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, config.get("toc_title", "Contenido"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(3)
    # Separator line
    pdf.set_draw_color(*primary_rgb)
    pdf.set_line_width(0.5)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(5)
    
    y_toc = pdf.get_y()
    toc_entries = []
    for i, mod in enumerate(modulos, 1):
        mod_name = mod.get("nombre", f"Seccion {i}")
        # Number
        pdf.set_font(_font_family, "B", size=10)
        pdf.set_text_color(*primary_rgb)
        pdf.cell(15, 6, f"{i}.", align="R")
        # Name
        pdf.set_font(_font_family, size=10)
        pdf.set_text_color(51, 65, 85)
        pdf.cell(130, 6, mod_name, align="L")
        
        # Dotted line to page number
        pdf.set_draw_color(203, 213, 225)
        pdf.set_line_width(0.1)
        y_line = pdf.get_y() - 3
        pdf.line(25, y_line, 160, y_line)
        
        # Page number (right aligned) - use x=160, w=40 to position correctly
        toc_entries.append({"y": y_line, "page": i + 1})
        pdf.set_x(160)
        pdf.set_font(_font_family, "B", size=9)
        pdf.set_text_color(*primary_rgb)
        pdf.cell(40, 6, str(i + 1), align="R")
        pdf.ln(2)
    # --- Sections per module ---
    module_start_pages = []
    for mod_idx, mod in enumerate(modulos):
        mod_name = mod.get("nombre", "Modulo")
        pdf._current_module = mod_name
        pdf.add_page()
        module_start_pages.append(pdf.page_no())

        # KPIs
        kpis = mod.get("kpis", [])
        if kpis:
            num_kpis = len(kpis)
            col_width = (190 - (num_kpis - 1) * 5) / num_kpis
            x_start = 10
            for i, kpi_cfg in enumerate(kpis):
                val = execute_kpi(kpi_cfg, filter_config, filter_values)
                formatted = _format_kpi_value(val, kpi_cfg.get("formato", "number"))
                label = kpi_cfg.get("label", "")
                sub_label = kpi_cfg.get("sub_label", "")

                x_pos = x_start + i * (col_width + 5)
                y_pos = pdf.get_y()

                # Card with rounded corners and shadow effect
                # Shadow
                pdf.set_fill_color(200, 210, 220)
                _draw_rounded_rect(pdf, x_pos + 0.5, y_pos + 0.5, col_width, 35, 2, "F")
                
                # Main card
                pdf.set_fill_color(255, 255, 255)
                _draw_rounded_rect(pdf, x_pos, y_pos, col_width, 35, 2, "F")
                
                # Border
                pdf.set_draw_color(226, 232, 240)
                pdf.set_line_width(0.3)
                _draw_rounded_rect(pdf, x_pos, y_pos, col_width, 35, 2, "D")
                
                # Top accent bar
                pdf.set_fill_color(*primary_rgb)
                pdf.rect(x_pos, y_pos, col_width, 2, "F")
                
                # Label
                pdf.set_xy(x_pos + 4, y_pos + 5)
                pdf.set_font(_font_family, size=7)
                pdf.set_text_color(100, 116, 139)
                pdf.multi_cell(col_width - 8, 4, label.upper(), align="C")
                
                # Value
                pdf.set_xy(x_pos + 4, pdf.get_y() + 2)
                pdf.set_font(_font_family, "B", size=14)
                pdf.set_text_color(*primary_rgb)
                pdf.multi_cell(col_width - 8, 6, formatted, align="C")
                
                # Sub label
                if sub_label:
                    pdf.set_xy(x_pos + 4, pdf.get_y() + 1)
                    pdf.set_font(_font_family, size=6)
                    pdf.set_text_color(148, 163, 184)
                    pdf.multi_cell(col_width - 8, 3, sub_label, align="C")

            pdf.ln(10)

        # Charts
        charts = mod.get("graficos", [])
        for chart_cfg in charts:
            title = chart_cfg.get("titulo", "Grafico")
            subtitle = chart_cfg.get("sub", "")

            # Execute query
            df = execute_query(chart_cfg, filter_config, filter_values)
            if df.empty:
                pdf.set_font(_font_family, "B", size=11)
                pdf.set_text_color(51, 65, 85)
                pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(_font_family, size=9)
                pdf.set_text_color(148, 163, 184)
                pdf.cell(0, 6, config.get("empty_msg", "Sin datos disponibles"), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(4)
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

            # Build chart config
            chart_build_cfg = {
                "tipo": chart_cfg.get("tipo", "bar"),
                "alto": chart_cfg.get("alto", 350),
            }
            for key in ("x", "y", "columna", "valores", "color", "size"):
                if key in chart_cfg:
                    chart_build_cfg[key] = chart_cfg[key]

            # Title with accent
            pdf.set_font(_font_family, "B", size=11)
            pdf.set_text_color(51, 65, 85)
            pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
            
            if subtitle:
                pdf.set_font(_font_family, size=8)
                pdf.set_text_color(148, 163, 184)
                pdf.cell(0, 6, subtitle, new_x="LMARGIN", new_y="NEXT")
            
            # Separator line
            pdf.set_draw_color(*medium_primary)
            pdf.set_line_width(0.3)
            y_sep = pdf.get_y()
            pdf.line(10, y_sep, 200, y_sep)
            pdf.ln(3)

            # Chart image
            png_bytes = _chart_to_png(chart_build_cfg, df)
            if png_bytes:
                # Check if we need a new page for the chart
                available_height = pdf.h - pdf.get_y() - 25
                if available_height < 60:
                    pdf.add_page()
                    _draw_header(pdf, mod_name)

                img_x = pdf.get_x()
                img_y = pdf.get_y()
                img_width = 185
                # Estimate height maintaining aspect ratio (PNG is 2x scale)
                try:
                    from PIL import Image
                    img = Image.open(io.BytesIO(png_bytes))
                    aspect = img.size[1] / img.size[0]
                    img_height = img_width * aspect
                except Exception:
                    img_height = 90

                # Cap height to fit on page
                max_height = pdf.h - img_y - 30
                if img_height > max_height:
                    img_height = max_height
                    img_width = img_height / aspect if 'aspect' in dir() else 185

                # Card background for chart
                pdf.set_fill_color(255, 255, 255)
                pdf.set_draw_color(241, 245, 249)
                pdf.set_line_width(0.2)
                pdf.rect(img_x + 2, img_y - 2, img_width + 4, img_height + 4, "FD")

                pdf.image(png_bytes, x=img_x + 5, y=img_y, w=img_width)
                pdf.set_y(img_y + img_height + 8)
            else:
                pdf.set_font(_font_family, size=9)
                pdf.set_text_color(148, 163, 184)
                pdf.cell(0, 6, config.get("chart_empty_msg", "Gráfico no disponible"), new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(3)

        # Tables
        tables = mod.get("tablas", [])
        for table_cfg in tables:
            t_title = table_cfg.get("titulo", "Tabla")
            
            # Title with accent
            pdf.set_font(_font_family, "B", size=11)
            pdf.set_text_color(51, 65, 85)
            pdf.cell(0, 8, t_title, new_x="LMARGIN", new_y="NEXT")
            
            # Separator line
            pdf.set_draw_color(*medium_primary)
            pdf.set_line_width(0.3)
            y_sep = pdf.get_y()
            pdf.line(10, y_sep, 200, y_sep)
            pdf.ln(2)

            df = execute_query(table_cfg, filter_config, filter_values)
            limit = table_cfg.get("limite", 50)
            if df.empty:
                pdf.set_font(_font_family, size=9)
                pdf.set_text_color(148, 163, 184)
                pdf.cell(0, 6, config.get("empty_msg", "Sin datos disponibles"), new_x="LMARGIN", new_y="NEXT")
                continue

            df_display = df.head(limit)
            cols = list(df_display.columns)
            num_cols = len(cols)
            col_w = 190 / num_cols

            # Header row with primary color
            pdf.set_fill_color(*primary_rgb)
            pdf.set_font(_font_family, "B", size=8)
            pdf.set_text_color(255, 255, 255)
            for col in cols:
                pdf.cell(col_w, 7, str(col), border=1, fill=True, align="C", new_x="RIGHT")
            pdf.ln()

            # Data rows with alternating colors
            pdf.set_font(_font_family, size=7)
            for row_idx, (_, row) in enumerate(df_display.iterrows()):
                if row_idx % 2 == 0:
                    pdf.set_fill_color(248, 250, 252)
                else:
                    pdf.set_fill_color(255, 255, 255)
                
                pdf.set_text_color(71, 85, 105)
                for j, col in enumerate(cols):
                    val = str(row[col]) if pd.notna(row[col]) else ""
                    # Truncate long values
                    if len(val) > 25:
                        val = val[:22] + "..."
                    pdf.cell(col_w, 5, val, border=1, fill=True, align="C", new_x="RIGHT")
                pdf.ln()

            pdf.ln(5)

    # Output PDF bytes
    output = io.BytesIO()
    pdf.output(output)
    return output.getvalue()


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
