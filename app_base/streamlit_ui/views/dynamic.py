"""Generic dynamic module renderer.

Reads a module config dict from ui_config.json and renders:
- Page header (breadcrumbs, title, description)
- KPI cards (from SQL queries)
- Charts (from SQL queries + render_chart)
- Tables (from SQL queries)

No hardcoded column names, no hardcoded queries — everything from JSON.
"""
from __future__ import annotations

import streamlit as st

from .components import (
    close_card,
    page_header,
    fmt_money,
    fmt_num,
    fmt_short_money,
    kpi,
    open_card,
    render_chart,
)
from core.data import error_count, last_error
from core.tools import execute_kpi, execute_query, get_filter_options, get_date_range


def _format_value(value, fmt: str):
    """Format a KPI value based on the 'formato' field."""
    if value is None or value == 0:
        if fmt == "money":
            return "$0.00"
        return "0"
    if fmt == "money":
        return fmt_short_money(float(value))
    elif fmt == "int":
        return fmt_num(int(value))
    elif fmt == "percent":
        return f"{float(value):.1f}%"
    elif fmt == "str":
        return str(value)
    return str(value)


def _build_sub_label(kpi_config: dict, filter_config, filter_values) -> str:
    """Build the sub-label for a KPI card."""
    if "sub_label" in kpi_config:
        return kpi_config["sub_label"]

    if "sub_sql" in kpi_config:
        # Execute the sub_sql, not the main sql
        sub_config = dict(kpi_config)
        sub_config["sql"] = kpi_config["sub_sql"]
        sub_val = execute_kpi(sub_config, filter_config, filter_values)
        prefix = kpi_config.get("sub_prefix", "")
        suffix = kpi_config.get("sub_suffix", "")
        sub_format = kpi_config.get("sub_format", "int")
        formatted = _format_value(sub_val, sub_format)
        return f"{prefix}{formatted}{suffix}"

    return ""


def render(modulo_config: dict, filter_config: list[dict] | None = None,
           filter_values: dict | None = None) -> None:
    """Render a complete module page from JSON config.

    Args:
        modulo_config: The module dict from ui_config.json['modulos'].
        filter_config: Global filter definitions (for WHERE clause injection).
        filter_values: User-selected filter values.
    """
    mod_id = modulo_config.get("id", "unknown")
    name = modulo_config.get("nombre", mod_id)
    material_icon = modulo_config.get("material_icon", "dashboard")
    breadcrumbs = modulo_config.get("breadcrumbs", f"HOME  /  {mod_id.upper()}")
    description = modulo_config.get("descripcion", "")

    page_header(material_icon, name, breadcrumbs, description)
    errors_before = error_count()

    # --- KPIs (responsive flex row) ---
    kpis = modulo_config.get("kpis", [])
    if kpis:
        KPI_PER_ROW = 4
        for batch_start in range(0, len(kpis), KPI_PER_ROW):
            batch = kpis[batch_start:batch_start + KPI_PER_ROW]
            kpi_htmls = []
            for kpi_cfg in batch:
                val = execute_kpi(kpi_cfg, filter_config, filter_values)
                formatted = _format_value(val, kpi_cfg.get("formato", "number"))
                sub = _build_sub_label(kpi_cfg, filter_config, filter_values)
                color = kpi_cfg.get("color", "#246bfd")
                kpi_htmls.append(kpi(kpi_cfg.get("icono", "insights"), kpi_cfg.get("label", ""), formatted, sub, color))
            row_html = '<div class="kpi-row">' + "".join(kpi_htmls) + '</div>'
            st.markdown(row_html, unsafe_allow_html=True)
            st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

    # --- Charts ---
    charts = modulo_config.get("graficos", [])

    # Group charts into rows: pairs with col_izq go side-by-side, full-width go alone
    i = 0
    while i < len(charts):
        g = charts[i]
        col_izq = g.get("col_izq")

        if col_izq is not None and i + 1 < len(charts) and charts[i + 1].get("col_izq") is not None:
            # Side-by-side pair
            g2 = charts[i + 1]
            col_der = g2.get("col_izq", 1)
            izq, der = st.columns([col_izq, col_der])

            with izq:
                _render_single_chart(g, filter_config, filter_values)

            with der:
                _render_single_chart(g2, filter_config, filter_values)

            i += 2
        else:
            # Full-width chart
            _render_single_chart(g, filter_config, filter_values)
            i += 1

        if i < len(charts):
            st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

    # --- Tables ---
    tables = modulo_config.get("tablas", [])
    for table_cfg in tables:
        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
        st.markdown(
            open_card(table_cfg["titulo"], table_cfg.get("sub", ""), table_cfg.get("icono", "table_chart")),
            unsafe_allow_html=True,
        )
        df = execute_query(table_cfg, filter_config, filter_values)
        limit = table_cfg.get("limite", 200)
        height = table_cfg.get("altura", 360)
        if not df.empty:
            st.dataframe(df.head(limit), width="stretch", hide_index=True, height=height)
        else:
            st.info("No data available for this table.")
        st.markdown(close_card(), unsafe_allow_html=True)

    # A failing query used to degrade silently into "$0 / empty chart".
    # Surface it once per page so the demo never looks broken for no reason.
    if error_count() != errors_before:
        with st.expander("⚠️ Some queries in this module failed", expanded=False):
            st.code(last_error() or "Unknown SQL error")


def _render_single_chart(g: dict, filter_config, filter_values) -> None:
    """Render a single chart card with data from SQL."""
    title = g.get("titulo", "Chart")
    subtitle = g.get("sub", "")
    icon = g.get("icono", "insights")

    st.markdown(open_card(title, subtitle, icon), unsafe_allow_html=True)

    # Execute the SQL query
    df = execute_query(g, filter_config, filter_values)

    if df.empty:
        st.info("No data for this chart.")
        st.markdown(close_card(), unsafe_allow_html=True)
        return

    # Apply column renames if specified
    rename = g.get("rename", {})
    if rename:
        df = df.rename(columns=rename)

    # Apply top_n filter for stacked charts
    top_n = g.get("top_n")
    if top_n and "x" in g:
        x_col = g["x"]
        if x_col in df.columns:
            top_values = df[x_col].value_counts().head(top_n).index.tolist()
            df = df[df[x_col].isin(top_values)]

    # Build chart config for render_chart
    chart_config = {
        "tipo": g.get("tipo", "bar"),
        "alto": g.get("alto", 350),
    }
    for key in ("x", "y", "columna", "valores", "color", "size"):
        if key in g:
            chart_config[key] = g[key]

    render_chart(chart_config, df)
    st.markdown(close_card(), unsafe_allow_html=True)
