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
    encabezado_pagina,
    fmt_money,
    fmt_num,
    fmt_short_money,
    kpi,
    open_card,
    render_chart,
)
from core.data import error_seq, ultimo_error
from core.tools import ejecutar_kpi, ejecutar_query, obtener_opciones_filtro, obtener_rango_fechas


def _format_value(valor, formato: str):
    """Format a KPI value based on the 'formato' field."""
    if valor is None or valor == 0:
        if formato == "money":
            return "$0.00"
        return "0"
    if formato == "money":
        return fmt_short_money(float(valor))
    elif formato == "int":
        return fmt_num(int(valor))
    elif formato == "percent":
        return f"{float(valor):.1f}%"
    elif formato == "str":
        return str(valor)
    return str(valor)


def _build_sub_label(kpi_config: dict, filtros_config, filtros_valores) -> str:
    """Build the sub-label for a KPI card."""
    if "sub_label" in kpi_config:
        return kpi_config["sub_label"]

    if "sub_sql" in kpi_config:
        # Execute the sub_sql, not the main sql
        sub_config = dict(kpi_config)
        sub_config["sql"] = kpi_config["sub_sql"]
        sub_val = ejecutar_kpi(sub_config, filtros_config, filtros_valores)
        prefix = kpi_config.get("sub_prefix", "")
        suffix = kpi_config.get("sub_suffix", "")
        sub_format = kpi_config.get("sub_format", "int")
        formatted = _format_value(sub_val, sub_format)
        return f"{prefix}{formatted}{suffix}"

    return ""


def render(modulo_config: dict, filtros_config: list[dict] | None = None,
           filtros_valores: dict | None = None) -> None:
    """Render a complete module page from JSON config.

    Args:
        modulo_config: The module dict from ui_config.json['modulos'].
        filtros_config: Global filter definitions (for WHERE clause injection).
        filtros_valores: User-selected filter values.
    """
    mod_id = modulo_config.get("id", "unknown")
    nombre = modulo_config.get("nombre", mod_id)
    material_icon = modulo_config.get("material_icon", "dashboard")
    breadcrumbs = modulo_config.get("breadcrumbs", f"HOME  /  {mod_id.upper()}")
    descripcion = modulo_config.get("descripcion", "")

    encabezado_pagina(material_icon, nombre, breadcrumbs, descripcion)
    errores_iniciales = error_seq()

    # --- KPIs (max 4 per row, equal height) ---
    kpis = modulo_config.get("kpis", [])
    if kpis:
        KPI_PER_ROW = 4
        for batch_start in range(0, len(kpis), KPI_PER_ROW):
            batch = kpis[batch_start:batch_start + KPI_PER_ROW]
            # Collect all KPI HTML first, then wrap in flex container
            kpi_htmls = []
            for kpi_cfg in batch:
                valor = ejecutar_kpi(kpi_cfg, filtros_config, filtros_valores)
                formatted = _format_value(valor, kpi_cfg.get("formato", "number"))
                sub = _build_sub_label(kpi_cfg, filtros_config, filtros_valores)
                color = kpi_cfg.get("color", "#246bfd")
                kpi_htmls.append(kpi(kpi_cfg["icono"], kpi_cfg["label"], formatted, sub, color))
            # Wrap in flex row so all cards have equal height
            row_html = '<div style="display:flex;gap:16px;">' + "".join(kpi_htmls) + '</div>'
            st.markdown(row_html, unsafe_allow_html=True)
            st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

    # --- Charts ---
    graficos = modulo_config.get("graficos", [])

    # Group charts into rows: pairs with col_izq go side-by-side, full-width go alone
    i = 0
    while i < len(graficos):
        g = graficos[i]
        col_izq = g.get("col_izq")

        if col_izq is not None and i + 1 < len(graficos) and graficos[i + 1].get("col_izq") is not None:
            # Side-by-side pair
            g2 = graficos[i + 1]
            col_der = g2.get("col_izq", 1)
            izq, der = st.columns([col_izq, col_der])

            with izq:
                _render_single_chart(g, filtros_config, filtros_valores)

            with der:
                _render_single_chart(g2, filtros_config, filtros_valores)

            i += 2
        else:
            # Full-width chart
            _render_single_chart(g, filtros_config, filtros_valores)
            i += 1

        if i < len(graficos):
            st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

    # --- Tables ---
    tablas = modulo_config.get("tablas", [])
    for tabla_cfg in tablas:
        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
        st.markdown(
            open_card(tabla_cfg["titulo"], tabla_cfg.get("sub", ""), tabla_cfg.get("icono", "table_chart")),
            unsafe_allow_html=True,
        )
        df = ejecutar_query(tabla_cfg, filtros_config, filtros_valores)
        limite = tabla_cfg.get("limite", 200)
        altura = tabla_cfg.get("altura", 360)
        if not df.empty:
            st.dataframe(df.head(limite), width="stretch", hide_index=True, height=altura)
        else:
            st.info("No data available for this table.")
        st.markdown(close_card(), unsafe_allow_html=True)

    # A failing query used to degrade silently into "$0 / empty chart".
    # Surface it once per page so the demo never looks broken for no reason.
    if error_seq() != errores_iniciales:
        with st.expander("⚠️ Some queries in this module failed", expanded=False):
            st.code(ultimo_error() or "Unknown SQL error")


def _render_single_chart(g: dict, filtros_config, filtros_valores) -> None:
    """Render a single chart card with data from SQL."""
    titulo = g.get("titulo", "Chart")
    sub = g.get("sub", "")
    icono = g.get("icono", "insights")

    st.markdown(open_card(titulo, sub, icono), unsafe_allow_html=True)

    # Execute the SQL query
    df = ejecutar_query(g, filtros_config, filtros_valores)

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
