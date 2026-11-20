"""Dynamic UI entry point — 100% JSON driven.

Reads ``ui_config.json`` for everything: modules, KPIs, charts, filters, SQL.
No hardcoded views, no hardcoded queries, no hardcoded column names.
The future MCP server will write this JSON; the UI just renders it.
"""
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

import json

import streamlit as st

from core.data import (
    archivo_en_uso,
    guardar_archivos,
    hay_datos,
    limpiar_datos,
    tablas_disponibles,
)
from core.tools import obtener_opciones_filtro, obtener_rango_fechas
from streamlit_ui import styles

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


def cargar_config() -> dict:
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
        ultimo = st.session_state.get(_LAST_GOOD_KEY)
        if ultimo is not None:
            return ultimo
        if CONFIG_PATH.exists():
            print(f"[ui_config] cannot parse {CONFIG_PATH}: {exc}")
        return DEFAULT_CONFIG


@st.fragment(run_every=2.0)
def _vigilar_config() -> None:
    """Cheap watcher: rerun the app only when ui_config.json actually changed.

    This replaces the old 3 s full ``st_autorefresh``, which re-executed every
    KPI, chart and table against DuckDB even when nothing had changed.
    """
    actual = _config_mtime()
    previo = st.session_state.get(_CONFIG_MTIME_KEY)
    if previo is None:
        st.session_state[_CONFIG_MTIME_KEY] = actual
        return
    if actual != previo:
        st.session_state[_CONFIG_MTIME_KEY] = actual
        st.rerun(scope="app")


# --------------------------------------------------------------------------- #
# Dynamic view renderer (replaces hardcoded VIEWS dict)
# --------------------------------------------------------------------------- #
from streamlit_ui.views.dynamic import render as render_modulo  # noqa: E402

# --------------------------------------------------------------------------- #
# Sidebar helpers
# --------------------------------------------------------------------------- #
def _marca(config: dict) -> None:
    brand_name = config.get("brand_name", "Dashboard")
    brand_sub = config.get("brand_sub", "")
    brand_icon = config.get("brand_icon", "storefront")
    st.markdown(
        f"""
        <div class="brand">
            <span class="brand-ic"><span class="mi">{brand_icon}</span></span>
            <div>
                <div class="brand-name">{brand_name}</div>
                <div class="brand-sub">{brand_sub}</div>
            </div>
        </div>
        <div class="side-sep"></div>
        """,
        unsafe_allow_html=True,
    )


def _navegacion(config: dict) -> str:
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


def _procesar_archivos() -> None:
    archivos = st.session_state.get("data_files")
    if archivos:
        guardar_archivos(archivos)


def _datos(config: dict) -> None:
    st.markdown('<div class="side-label">Data Source</div>', unsafe_allow_html=True)

    st.file_uploader(
        "Upload CSV / Excel files",
        type=["csv", "xlsx"],
        accept_multiple_files=True,
        key="data_files",
        on_change=_procesar_archivos,
        help="Drop your data files (CSV or Excel XLSX). The app will auto-detect the type.",
        disabled=False,
    )

    # Show all available tables dynamically
    if hay_datos():
        tables = tablas_disponibles()
        if tables:
            files_lines = ""
            for t in sorted(tables):
                label = t.capitalize()
                file_name = archivo_en_uso(t)
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

    if hay_datos() and st.button(
        "Clear all data", width="stretch", icon=":material/delete:",
        disabled=False
    ):
        limpiar_datos()
        st.rerun()

    st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)


def _filtros_globales(config: dict) -> dict:
    """Render global filters dynamically from JSON config."""
    st.markdown('<div class="side-label">Global Filters</div>', unsafe_allow_html=True)

    filtros_config = config.get("filtros_globales", [])
    if not filtros_config or not hay_datos():
        st.caption("Upload data to enable the global filters.")
        st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
        return {}

    valores: dict = {}
    for f_cfg in filtros_config:
        nombre = f_cfg["nombre"]
        etiqueta = f_cfg.get("etiqueta", nombre)
        f_tipo = f_cfg.get("tipo", "select")

        if f_tipo == "select":
            opciones = obtener_opciones_filtro(f_cfg)
            todos_label = f_cfg.get("todos_label", "All")
            opciones_con_todo = [todos_label] + opciones
            sel = st.selectbox(etiqueta, opciones_con_todo)
            valores[nombre] = "All" if sel == todos_label else sel

        elif f_tipo == "date_range":
            f_min, f_max = obtener_rango_fechas(f_cfg)
            if f_min is not None and f_max is not None and f_min < f_max:
                fecha = st.slider(etiqueta, min_value=f_min, max_value=f_max,
                                  value=(f_min, f_max), format="YYYY-MM-DD")
                valores[nombre] = fecha
            else:
                # Column is not a real date (e.g. Year integer) — fall back to select
                opciones = obtener_opciones_filtro(f_cfg)
                if opciones:
                    sel = st.selectbox(etiqueta, ["All"] + opciones)
                    valores[nombre] = None if sel == "All" else sel
                else:
                    valores[nombre] = None

        elif f_tipo == "multiselect":
            opciones = obtener_opciones_filtro(f_cfg)
            sel = st.multiselect(etiqueta, opciones, default=opciones,
                                 placeholder="All")
            valores[nombre] = sel if sel else opciones

    st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
    return valores


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    # Live-reload config: pick up MCP edits without restarting the server.
    config = cargar_config()

    st.set_page_config(
        page_title=config.get("titulo_pagina", "Dashboard"),
        page_icon=":material/" + config.get("brand_icon", "storefront") + ":",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _vigilar_config()
    styles.aplicar_estilos()

    with st.sidebar:
        _marca(config)
        modulo_id = _navegacion(config)
        _datos(config)
        filtros_valores = _filtros_globales(config)
        st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
        # Dynamic sidebar disclaimer from config
        disclaimer = config.get("sidebar_disclaimer", "")
        if disclaimer:
            st.markdown(
                f'<p style="color: var(--body); opacity: 0.7; font-size: 0.8rem; line-height: 1.5; margin: 0.5rem 0 0 0;">{disclaimer}</p>',
                unsafe_allow_html=True,
            )

    # Empty state — read from config
    if not hay_datos():
        empty_title = config.get("empty_state", {}).get("title")
        empty_desc = config.get("empty_state", {}).get("description")
        empty_hint = config.get("empty_state", {}).get("hint")
        styles.render_estado_sin_datos(
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
    filtros_config = config.get("filtros_globales", [])

    # Render the module dynamically — everything from JSON
    render_modulo(modulo_config, filtros_config=filtros_config, filtros_valores=filtros_valores)

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
    import os
    import subprocess
    import sys

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
