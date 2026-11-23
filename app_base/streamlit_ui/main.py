"""Dynamic UI entry point — 100% JSON driven.

Reads ``ui_config.json`` for everything: modules, KPIs, charts, filters, SQL.
No hardcoded views, no hardcoded queries, no hardcoded column names.
The future MCP server will write this JSON; the UI just renders it.
"""
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Ensure importable paths regardless of whether Streamlit is launched from the
# repository root, from app_base/ or directly from streamlit_ui/:
#   - repo root  -> `import app_base.*`
#   - app_base/  -> `import core.*` / `import streamlit_ui.*`
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PROJECT_ROOT.parent if (_PROJECT_ROOT.parent / "app_base").is_dir() else _PROJECT_ROOT
for _p in (str(_REPO_ROOT), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd
import streamlit as st

from core.data import (
    available_tables,
    file_in_use,
    has_data,
    ingest_table,
)
from core.tools import get_filter_options, get_date_range
from streamlit_ui import styles
from streamlit_ui.views.dynamic import render as render_modulo

# --------------------------------------------------------------------------- #
# Config loader
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "ui_config.json"

DEFAULT_CONFIG = {
    "titulo_pagina": "Dashboard",
    "brand_name": "Dashboard",
    "brand_sub": "",
    "filtros_globales": [],
    "modulos": [],
    "sidebar_disclaimer": "",
    "footer": "",
}


_CONFIG_MTIME_KEY = "_ui_config_mtime"
_LAST_GOOD_KEY = "_ui_config_last_good"


def _config_mtime() -> float:
    """Modification time of ui_config.json (0.0 when missing)."""
    try:
        return CONFIG_PATH.stat().st_mtime
    except OSError:
        return 0.0


def load_config() -> dict:
    """Load ui_config.json on every run so MCP edits show up immediately.

    No caching: the file is ~15 KB, so re-reading it costs less than the
    rerun itself. If the file is momentarily unreadable (the MCP server is
    writing it), the last good config from this session is reused instead
    of flashing the empty default dashboard.
    """
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict):
            raise ValueError("ui_config.json must contain a JSON object")
        st.session_state[_LAST_GOOD_KEY] = config
        return config
    except Exception as exc:
        last_good = st.session_state.get(_LAST_GOOD_KEY)
        if last_good is not None:
            return last_good
        if CONFIG_PATH.exists():
            print(f"[ui_config] cannot parse {CONFIG_PATH}: {exc}")
        return DEFAULT_CONFIG


@st.fragment(run_every=2.0)
def _watch_config() -> None:
    """Cheap watcher: rerun the app only when ui_config.json actually changed.

    This replaces the old 3 s full ``st_autorefresh``, which re-executed every
    KPI, chart and table against DuckDB even when nothing had changed.
    """
    actual = _config_mtime()
    prev_mtime = st.session_state.get(_CONFIG_MTIME_KEY)
    if prev_mtime is None:
        st.session_state[_CONFIG_MTIME_KEY] = actual
        return
    if actual != prev_mtime:
        st.session_state[_CONFIG_MTIME_KEY] = actual
        st.rerun(scope="app")


# --------------------------------------------------------------------------- #
# Sidebar helpers
# --------------------------------------------------------------------------- #
def _brand(config: dict) -> None:
    brand_name = config.get("brand_name", "Dashboard")
    brand_sub = config.get("brand_sub", "")
    brand_icon = config.get("brand_icon", "storefront")
    brand_logo = config.get("brand_logo", "")

    # Build the logo area: image (URL or local file) falls back to Material Icon
    if brand_logo:
        if brand_logo.startswith(("http://", "https://")):
            logo_html = f'<img class="brand-logo-img" src="{brand_logo}" alt="{brand_name}" />'
        else:
            # Local file in app_base/assets/
            logo_path = BASE_DIR / "assets" / brand_logo
            if logo_path.is_file():
                import base64
                mime = "image/png" if brand_logo.endswith(".png") else "image/jpeg"
                b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
                logo_html = f'<img class="brand-logo-img" src="data:{mime};base64,{b64}" alt="{brand_name}" />'
            else:
                # File not found — fall back to icon
                logo_html = f'<span class="brand-ic"><span class="mi">{brand_icon}</span></span>'
    else:
        logo_html = f'<span class="brand-ic"><span class="mi">{brand_icon}</span></span>'

    st.markdown(
        f"""
        <div class="brand">
            {logo_html}
            <div>
                <div class="brand-name">{brand_name}</div>
                <div class="brand-sub">{brand_sub}</div>
            </div>
        </div>
        <div class="side-sep"></div>
        """,
        unsafe_allow_html=True,
    )


def _navigation(config: dict) -> str:
    """Dynamically build sidebar navigation from config['modulos']."""
    st.markdown('<div class="side-label">Modules</div>', unsafe_allow_html=True)
    modulos = config.get("modulos", [])
    etiquetas = [f"{m.get('icono', '📋')} {m.get('nombre', 'Module')}" for m in modulos]
    eleccion = st.radio(
        "Modules",
        etiquetas,
        label_visibility="collapsed",
    )
    idx = etiquetas.index(eleccion) if eleccion in etiquetas else 0
    st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
    return modulos[idx]["id"] if modulos else "dashboard"


def _get_expected_columns(config: dict, table: str) -> list[str]:
    """Extract expected column names for a table from column_mapping.

    The column_mapping uses keys like ``sales_sucursal``, ``sales_fecha``, etc.
    The values are the physical CSV/Excel header names. This function returns
    the sorted list of unique physical column names for the given table prefix.
    """
    col_map = config.get("column_mapping", {})
    prefix = table + "_"
    cols = [
        col for role, col in col_map.items()
        if role.startswith(prefix)
    ]
    # Deduplicate while preserving order
    seen = set()
    result = []
    for c in cols:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _read_file_columns(file) -> list[str]:
    """Read the header row of an uploaded CSV or Excel file and return column names."""
    try:
        data = file.getvalue()
        if file.name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(data), engine="calamine", nrows=0)
        else:
            df = pd.read_csv(io.BytesIO(data), nrows=0)
        return list(df.columns)
    except Exception:
        return []


def _process_data_update() -> None:
    """Handle the data update file upload: validate columns and replace data."""
    files = st.session_state.get("update_files")
    table = st.session_state.get("update_table")
    if not files or not table:
        return

    config = load_config()
    expected = _get_expected_columns(config, table)
    if not expected:
        # Fallback: no column_mapping for this table — accept any file
        expected = None

    uploaded = files[0]  # Take the first file
    actual = _read_file_columns(uploaded)

    if expected and actual:
        expected_set = set(expected)
        actual_set = set(actual)
        missing = expected_set - actual_set
        extra = actual_set - expected_set

        if missing:
            st.error(
                f"Column mismatch — missing: {', '.join(sorted(missing))}. "
                f"Please use a file with the original column names."
            )
            return
        if extra:
            st.warning(
                f"Extra columns found: {', '.join(sorted(extra))}. "
                f"Only the expected columns will be used."
            )

    # Replace the data
    try:
        messages = ingest_table(table, [uploaded])
        for msg in messages:
            st.success(msg)
        st.rerun()
    except Exception as e:
        st.error(f"Failed to update data: {e}")


def _data_source(config: dict) -> None:
    st.markdown('<div class="side-label">Data Source</div>', unsafe_allow_html=True)

    # Data update — only for refreshing previously loaded data, NOT for creating dashboards
    if has_data():
        tables = available_tables()
        if tables:
            st.markdown(
                '<p style="font-size:0.75rem; color:var(--body); opacity:0.6; margin:0 0 0.5rem 0;">'
                "Refresh data from previously loaded files only. "
                "This does not create a new dashboard."
                '</p>',
                unsafe_allow_html=True,
            )
            update_table = st.selectbox(
                "Table to update",
                tables,
                key="update_table",
                help="Select which table's data you want to refresh with a new file.",
            )
            st.file_uploader(
                "Refresh data",
                type=["csv", "xlsx"],
                accept_multiple_files=False,
                key="update_files",
                on_change=_process_data_update,
                help="Upload a CSV or Excel with the same columns to update this table's data.",
            )
            st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)

    # Show all available tables dynamically
    if has_data():
        tables = available_tables()
        if tables:
            files_lines = ""
            for t in sorted(tables):
                label = t.capitalize()
                file_name = file_in_use(t)
                files_lines += f"{label}: <b>{file_name}</b><br>"
        else:
            files_lines = "No tables found."

        st.markdown(
            f"""
            <span style="background: var(--bg); border:1px solid var(--border); border-radius:10px;
                        padding:10px 12px; font-size:0.82rem; color: var(--body); line-height:1.7;
                        display:inline-block;">
                <span class="mi" style="font-size:0.95rem; vertical-align:-2px;">folder_open</span>
                <b style="color:var(--head);">Files in use</b>
                <span style="opacity:0.85; display:block; margin-top:4px;">
                    {files_lines}
                </span>
            </span>
            """,
            unsafe_allow_html=True,
        )
    
    st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)


def _global_filters(config: dict) -> dict:
    """Render global filters dynamically from JSON config."""
    st.markdown('<div class="side-label">Global Filters</div>', unsafe_allow_html=True)

    filter_config = config.get("filtros_globales", [])
    if not filter_config or not has_data():
        st.caption("Upload data to enable the global filters.")
        st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
        return {}

    values: dict = {}
    for f_cfg in filter_config:
        nombre = f_cfg["nombre"]
        etiqueta = f_cfg.get("etiqueta", nombre)
        f_tipo = f_cfg.get("tipo", "select")

        if f_tipo == "select":
            options = get_filter_options(f_cfg)
            todos_label = f_cfg.get("todos_label", "All")
            options_with_all = [todos_label] + options
            sel = st.selectbox(etiqueta, options_with_all)
            values[nombre] = "All" if sel == todos_label else sel

        elif f_tipo == "date_range":
            f_min, f_max = get_date_range(f_cfg)
            if f_min is not None and f_max is not None and f_min < f_max:
                fecha = st.slider(etiqueta, min_value=f_min, max_value=f_max,
                                  value=(f_min, f_max), format="YYYY-MM-DD")
                values[nombre] = fecha
            else:
                # Column is not a real date (e.g. Year integer) — fall back to select
                options = get_filter_options(f_cfg)
                if options:
                    sel = st.selectbox(etiqueta, ["All"] + options)
                    values[nombre] = None if sel == "All" else sel
                else:
                    values[nombre] = None

        elif f_tipo == "multiselect":
            options = get_filter_options(f_cfg)
            sel = st.multiselect(etiqueta, options, default=options,
                                 placeholder="All")
            values[nombre] = sel if sel else options

    st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
    return values


def _pdf_export_button(config: dict, filter_values: dict) -> None:
    """PDF export button in the sidebar.

    Generates the PDF lazily only when the user clicks the button, not on
    every rerun.  The download is offered via ``st.download_button`` so the
    browser handles the file save.
    """
    if not has_data():
        return

    st.markdown('<div class="side-label">Export</div>', unsafe_allow_html=True)

    clicked = st.button("Exportar a PDF", use_container_width=True, type="secondary")

    if clicked:
        try:
            from core.pdf_export import generate_pdf
        except ImportError as exc:
            st.error(f"No se puede generar el PDF: {exc}")
            return

        with st.spinner("Generando PDF..."):
            pdf_bytes = generate_pdf(config, filter_values)

        # Build a clean file name from brand_name
        brand = config.get("brand_name", "Dashboard")
        safe_name = re.sub(r"[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]", "", brand).strip().replace(" ", "_")
        file_name = f"{safe_name}.pdf"

        st.download_button(
            label="Descargar PDF",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            use_container_width=True,
            type="secondary",
        )

    st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    # Live-reload config: pick up MCP edits without restarting the server.
    config = load_config()

    st.set_page_config(
        page_title=config.get("titulo_pagina", "Dashboard"),
        page_icon=":material/" + config.get("brand_icon", "storefront") + ":",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _watch_config()
    primary_color = config.get("primary_color")
    styles.apply_styles(primary_color=primary_color)

    with st.sidebar:
        _brand(config)
        modulo_id = _navigation(config)
        _data_source(config)
        filter_values = _global_filters(config)
        _pdf_export_button(config, filter_values)
        st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
        # Dynamic sidebar disclaimer from config
        disclaimer = config.get("sidebar_disclaimer", "")
        if disclaimer:
            st.markdown(
                f'<p style="color: var(--body); opacity: 0.7; font-size: 0.8rem; line-height: 1.5; margin: 0.5rem 0 0 0;">{disclaimer}</p>',
                unsafe_allow_html=True,
            )

    # Empty state — read from config
    if not has_data():
        empty_title = config.get("empty_state", {}).get("title")
        empty_desc = config.get("empty_state", {}).get("description")
        empty_hint = config.get("empty_state", {}).get("hint")
        styles.render_empty_state(
            empty_state_title=empty_title,
            empty_state_desc=empty_desc,
            empty_state_hint=empty_hint,
        )
        st.stop()

    # Find the module config from JSON
    modulos = config.get("modulos", [])
    modulo_config = next((m for m in modulos if m["id"] == modulo_id), None)

    if modulo_config is None:
        st.info(f"Module '{modulo_id}' is not configured in ui_config.json.")
        return

    # Get filter config for WHERE clause injection
    filter_config = config.get("filtros_globales", [])

    # Render the module dynamically — everything from JSON
    render_modulo(modulo_config, filter_config=filter_config, filter_values=filter_values, primary_color=primary_color)

    # Footer — dynamic from config
    footer_text = config.get("footer", "")
    if footer_text:
        st.markdown(f'<div class="footer">{footer_text}</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()


def cli_entrypoint():
    """Entry point for the 'ui' console script — launches Streamlit.

    Streamlit only reads ``.streamlit/config.toml`` from the *current working
    directory* (plus the user's global config). Launching from the repository
    root used to skip ``app_base/.streamlit/config.toml``, so the app fell back
    to the default theme (primary red + dark mode on dark OS) while our custom
    CSS kept painting a light shell — the widgets turned black. We now pin the
    working directory (repo root, so ``import app_base.*`` keeps working) and
    pass the light theme explicitly via CLI flags (highest precedence), because
    Streamlit ignores ``STREAMLIT_THEME_*`` environment variables.

    The server binds IPv4 by default: on Windows + Python 3.14, Streamlit's
    default ``::`` bind intermittently dies with ``OSError [WinError 64]``.
    Override with ``AGENTUI_HOST`` (e.g. ``0.0.0.0`` to expose it on the LAN)
    and ``AGENTUI_PORT``.
    """
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent  # app_base/
    # Repo root contains the `app_base` package; running from there keeps the
    # absolute `app_base.*` imports valid.
    repo_root = project_root.parent if (project_root.parent / "app_base").is_dir() else project_root

    host = os.environ.get("AGENTUI_HOST", "127.0.0.1")
    port = os.environ.get("AGENTUI_PORT", "8501")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(script_path),
            f"--server.address={host}",
            f"--server.port={port}",
            "--theme.base=light",
            "--theme.primaryColor=#246bfd",
            "--theme.backgroundColor=#f8fafc",
            "--theme.secondaryBackgroundColor=#ffffff",
            "--theme.textColor=#0f172a",
        ],
        cwd=str(repo_root),
    )
