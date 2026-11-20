"""agentui-mcp — exposes app tools for AI agents via Model Context Protocol.

This server uses FastMCP with stdio transport so an AI agent (Claude, Cursor,
etc.) can call tools like `upload_csv`, `generate_config`, `run_query`, etc.

Usage:
    python server.py              # runs as stdio server
    # Or configure in your AI client:
    #   command: python
    #   args:    ["server.py"]
    #   cwd:     path/to/agentui-mcp
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

# Ensure the project root (app_base/) is on sys.path so `core` is importable.
# agentui-mcp sits next to app_base/, so parent is the repo root, then app_base/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent / "app_base"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastmcp import FastMCP

import pandas as pd

# Import app modules
from core.data import (
    close_con,
    ingestir_tabla,
    limpiar_datos,
    hay_datos,
    tabla_existe,
    tablas_disponibles,
    archivo_en_uso,
    ejecutar,
    ultimo_error,
    error_seq,
    UPLOAD_DIR,
    DB_PATH,
)
from core.inference import (
    generar_ui_config,
    _ROLES,
    _detectar_columnas_fisicas,
    _clasificar_columnas,
)
from core.tools import (
    ejecutar_query,
    ejecutar_kpi,
    obtener_opciones_filtro,
    obtener_rango_fechas,
    actualizar_ui_config,
    cargar_config,
)
from core.chart_builder import (
    CHART_TYPES,
    recomendar_grafica,
    construir_config_grafico,
    construir_config_kpi,
    construir_config_filtro,
    construir_config_modulo,
    listar_tipos_grafica,
)

# --------------------------------------------------------------------------- #
# MCP Server
# --------------------------------------------------------------------------- #

mcp = FastMCP(
    name="AgentUI Dashboard",
    instructions=(
        "You are a dashboard builder assistant. Your job is to turn CSV/Excel files into "
        "interactive analytics dashboards automatically. You control everything through MCP tools — "
        "no code changes are ever needed.\n\n"
        "========================================================================\n"
        "ARCHITECTURE (Dumb Skeleton)\n"
        "========================================================================\n\n"
        "The Streamlit UI is a blind renderer. It reads `ui_config.json` and displays "
        "whatever it finds: KPIs, charts, filters, tables, navigation. If you change "
        "the JSON, the UI changes automatically (auto-refreshes every 3 seconds).\n\n"
        "Data flow: CSV → DuckDB → column detection → ui_config.json → Streamlit UI.\n\n"
        "========================================================================\n"
        "⚡ QUICK START — create_dashboard() does EVERYTHING\n"
        "========================================================================\n\n"
        "When a user gives you a CSV/Excel file and asks for a dashboard, call:\n\n"
        "  create_dashboard(file_path='<path>', dashboard_name='<title>')\n\n"
        "This single tool:\n"
        "  1. Uploads the file to DuckDB\n"
        "  2. Analyzes columns and auto-generates KPIs, charts, and filters\n"
        "  3. Saves ui_config.json\n"
        "  4. STARTS the Streamlit server automatically\n"
        "  5. Returns the URL to open in the browser\n\n"
        "After create_dashboard() returns, ALWAYS tell the user the URL.\n\n"
        "========================================================================\n"
        "🧠 DASHBOARD QUALITY — Always verify and enrich\n"
        "========================================================================\n\n"
        "After create_dashboard() completes, CHECK the quality:\n\n"
        "  1. Call get_config() to see what was generated\n"
        "  2. Count the KPIs and charts in the response\n"
        "  3. If the dashboard has fewer than 3 KPIs or fewer than 2 charts:\n"
        "     a. Call explore_data(table_name) to understand the data\n"
        "     b. Use the recommendations to build additional charts/KPIs\n"
        "     c. Call get_config(), add the new elements, and update_config()\n\n"
        "The system has a generic fallback that works with ANY data, but you can "
        "always make it better by adding custom charts based on what explore_data() suggests.\n\n"
        "========================================================================\n"
        "🔍 RECOMMENDED WORKFLOW — For the best dashboard\n"
        "========================================================================\n\n"
        "For a polished dashboard, follow this flow:\n\n"
        "  Step 1: upload_csv(file_path, table_name)  → load the data\n"
        "  Step 2: preview_table(table_name, 10)      → see first 10 rows\n"
        "  Step 3: explore_data(table_name)            → understand columns & get recommendations\n"
        "  Step 4: generate_config()                   → auto-generate base dashboard\n"
        "  Step 5: get_config()                        → review what was generated\n"
        "  Step 6: Enrich the dashboard (if needed):\n"
        "          - Use build_chart_config() to add custom charts\n"
        "          - Use build_kpi_config() to add custom KPIs\n"
        "          - Modify the JSON and call update_config()\n"
        "  Step 7: start_streamlit()                   → start server if not running\n\n"
        "The dashboard auto-refreshes every 3 seconds. No restart needed.\n\n"
        "========================================================================\n"
        "STREAMLIT SERVER MANAGEMENT\n"
        "========================================================================\n\n"
        "start_streamlit(port) → Start server, returns URL (default port 8501)\n"
        "stop_streamlit() → Stop server\n"
        "check_streamlit_status() → Check if running\n\n"
        "create_dashboard() starts the server automatically. You only need manual\n"
        "management when customizing after the initial creation.\n\n"
        "========================================================================\n"
        "AVAILABLE TOOLS (25 total)\n"
        "========================================================================\n\n"
        "--- STREAMLIT (3) ---\n"
        "start_streamlit(port) — Start server, returns URL\n"
        "stop_streamlit() — Stop server\n"
        "check_streamlit_status() — Check status\n\n"
        "--- DATA (6) ---\n"
        "create_dashboard(file_path, dashboard_name) — ⭐ MAIN: all-in-one dashboard creator\n"
        "upload_csv(file_path, table_name) — Upload single file\n"
        "upload_multiple_csvs(file_paths, table_name) — Upload multiple files\n"
        "list_tables() — List loaded tables with row counts\n"
        "get_table_columns(table_name) — Show columns and types\n"
        "preview_table(table_name, limit) — Preview first N rows as CSV\n"
        "explore_data(table_name) — 🔍 Full data exploration with recommendations\n"
        "clear_data() — Wipe all data and config\n\n"
        "--- CONFIG (4) ---\n"
        "generate_config() — Auto-generate ui_config.json from loaded data\n"
        "get_config() — Read current config (alias: load_config)\n"
        "load_config() — Same as get_config\n"
        "update_config(json_string) — Replace config with validated JSON\n\n"
        "--- QUERIES (3) ---\n"
        "run_query(sql) — Execute raw SQL, returns CSV\n"
        "run_query_with_filters(sql, filters_json) — SQL with dynamic filters\n"
        "get_kpi(kpi_json) — Execute KPI query, return formatted value\n\n"
        "--- FILTERS (2) ---\n"
        "get_filter_options(filter_json) — Distinct values for a filter\n"
        "get_date_range(filter_json) — Min/max date range\n\n"
        "--- DETECTION (2) ---\n"
        "detect_columns(table_name) — Map columns to logical roles\n"
        "get_available_roles() — List all detectable roles and synonyms\n\n"
        "--- CHART BUILDER (5) ---\n"
        "list_chart_types() — List 8 chart types with guidance\n"
        "recommend_chart(sql) — Recommend charts based on SQL results\n"
        "build_chart_config(chart_json) — Build chart config dict\n"
        "build_kpi_config(kpi_json) — Build KPI config dict\n"
        "build_filter_config(filter_json) — Build filter config dict\n"
        "build_module_config(module_json) — Build full module config dict\n\n"
        "========================================================================\n"
        "UI_CONFIG.JSON — COMPLETE STRUCTURE REFERENCE\n"
        "========================================================================\n\n"
        "The JSON has 3 main sections: filters, modules (pages), and metadata.\n\n"
        "--- TOP-LEVEL FIELDS ---\n"
        "  titulo_pagina: Browser tab title\n"
        "  brand_name: Sidebar brand text\n"
        "  brand_sub: Sidebar subtitle (optional)\n"
        "  brand_icon: Material icon name (e.g. \"dashboard\")\n"
        "  column_mapping: {\"role\": \"physical_column_name\"}  (info only)\n"
        "  sidebar_disclaimer: Footer text in sidebar (optional)\n"
        "  footer: Page footer text (optional)\n"
        "  empty_state: {\"title\": \"...\", \"description\": \"...\"}  (shown when no data)\n\n"
        "--- FILTROS_GLOBALES (Sidebar filters) ---\n"
        "  Each filter:\n"
        "    nombre: Unique key (e.g. \"branch\", \"date_range\")\n"
        "    etiqueta: Display label in sidebar\n"
        "    columna: Physical column name in DuckDB\n"
        "    tabla: DuckDB table name\n"
        "    tipo: \"select\" | \"multiselect\" | \"date_range\"\n"
        "    todos_label: (optional) Label for \"All\" option in select\n\n"
        "--- MODULOS (Dashboard pages) ---\n"
        "  Each module becomes a sidebar nav item + a page:\n"
        "    id: Unique slug (e.g. \"overview\", \"details\", \"inventory\")\n"
        "    nombre: Display name in sidebar\n"
        "    icono: Emoji (e.g. \"📊\")\n"
        "    descripcion: Short description text\n"
        "    material_icon: Material icon name\n"
        "    breadcrumbs: \"HOME  /  PAGE_NAME\"\n"
        "    kpis: [list of KPI cards]\n"
        "    graficos: [list of charts]\n"
        "    tablas: [list of data tables]  (optional)\n\n"
        "--- KPI CARD ---\n"
        "    icono: Material icon (e.g. \"payments\", \"receipt_long\", \"inventory_2\")\n"
        "    label: Short title (e.g. \"Total Sales\")\n"
        "    sql: SQL returning single value as \"v\" column\n"
        "    formato: \"money\" | \"int\" | \"float\" | \"str\"\n"
        "    color: Hex color (e.g. \"#246bfd\")\n"
        "    sub_label: (optional) Small text below value\n"
        "    sub_sql: (optional) Secondary SQL for sub-value\n"
        "    sub_prefix/sub_suffix: (optional) Text around sub-value\n\n"
        "--- CHART TYPES ---\n"
        "  bar: Vertical bar chart  →  x, y, titulo, sql\n"
        "  bar_h: Horizontal bar   →  x, y, titulo, sql\n"
        "  pie: Pie chart          →  columna, valores, titulo, sql\n"
        "  line: Line chart         →  x, y, titulo, sql\n"
        "  scatter: Scatter plot    →  x, y, color(optional), titulo, sql\n"
        "  heatmap: Heatmap         →  x, y, valores, titulo, sql\n"
        "  bar_grouped: Grouped bars →  x, y, group_by, titulo, sql\n"
        "  bar_stacked: Stacked bars →  x, y, stack_by, titulo, sql\n"
        "  Common: icono, sub(description), alto(height px), col_izq(width ratio)\n"
        "  ⚠️ Chart `color` field: If present, it must be a COLUMN NAME from your SQL result\n"
        "     (for grouping bars/lines by category). It is NOT a hex color code.\n"
        "     Omit `color` for single-color charts — the system auto-applies a palette.\n\n"
        "--- DATA TABLE ---\n"
        "    titulo: Display title\n"
        "    sub: Description text\n"
        "    icono: Material icon\n"
        "    sql: Full SELECT query\n"
        "    limite: Max rows (default 100)\n\n"
        "Example minimal JSON:\n"
        "{\n"
        "  \"titulo_pagina\": \"My Dashboard\",\n"
        "  \"brand_name\": \"My Dashboard\",\n"
        "  \"column_mapping\": {},\n"
        "  \"filtros_globales\": [],\n"
        "  \"modulos\": [\n"
        "    {\n"
        "      \"id\": \"overview\", \"nombre\": \"Overview\", \"icono\": \"📊\",\n"
        "      \"descripcion\": \"Summary\", \"material_icon\": \"dashboard\",\n"
        "      \"breadcrumbs\": \"HOME  /  OVERVIEW\",\n"
        "      \"kpis\": [{\"icono\": \"payments\", \"label\": \"Total\", \"sql\": \"SELECT SUM(amount) AS v FROM data\", \"formato\": \"money\", \"color\": \"#246bfd\"}],\n"
        "      \"graficos\": [{\"tipo\": \"bar\", \"titulo\": \"By Category\", \"sql\": \"SELECT category, SUM(amount) AS Total FROM data GROUP BY category\", \"x\": \"category\", \"y\": \"Total\"}]\n"
        "    }\n"
        "  ],\n"
        "  \"empty_state\": {\"title\": \"No data\", \"description\": \"Upload files to start.\"}\n"
        "}\n\n"
        "========================================================================\n"
        "⚠️ CRITICAL RULES — Read carefully to avoid dashboard errors\n"
        "========================================================================\n\n"
        "--- CHART `color` FIELD — Most Common Mistake ---\n"
        "  In CHARTS, the `color` field is a COLUMN NAME for grouping, NOT a hex color.\n"
        "  - ✅ Correct: \"color\": \"Country\"  (groups bars by Country column)\n"
        "  - ❌ WRONG:  \"color\": \"#246bfd\"  (this breaks the chart — hex colors are for KPIs only)\n"
        "  - If you want a single-color chart, simply OMIT the `color` field.\n"
        "  - The system automatically applies a color palette. You do NOT need to set colors on charts.\n\n"
        "  In KPIs, the `color` field IS a hex color for the card background.\n"
        "  - ✅ Correct: \"color\": \"#246bfd\"  (KPI card background color)\n\n"
        "--- SQL FILTER INJECTION — How Global Filters Work ---\n"
        "  Every SQL query in ui_config.json is automatically combined with global filters.\n"
        "  The system injects a WHERE clause for date ranges and country/branch filters.\n\n"
        "  Important rules for writing SQL:\n"
        "  1. Your SQL queries the base table directly (e.g. \"online_retail\").\n"
        "  2. If your SQL already has a WHERE clause, the system merges filters with AND.\n"
        "  3. For subqueries/CTEs: the filter columns (InvoiceDate, Country) must exist\n"
        "     in the subquery that reads from the base table, not in the outer query.\n"
        "  4. Example of a safe subquery:\n"
        "     WITH freq AS (\n"
        "       SELECT \"CustomerID\", COUNT(DISTINCT \"InvoiceNo\") AS num_facturas\n"
        "       FROM online_retail  ← filters inject here (InvoiceDate, Country exist)\n"
        "       GROUP BY \"CustomerID\"\n"
        "     ) SELECT CASE WHEN num_facturas <= 5 THEN '1-5' ... FROM freq GROUP BY rango\n\n"
        "  5. Avoid inline subqueries in FROM when filter columns don't exist in the subquery.\n"
        "     Use CTEs (WITH ... AS) instead — they are easier for the filter injector.\n\n"
        "--- CHART COLUMN REFERENCES ---\n"
        "  The `x`, `y`, `columna`, `valores` fields in charts must exactly match\n"
        "  the column aliases returned by your SQL query.\n"
        "  - If your SQL returns \"SELECT Country, SUM(...) AS ventas ...\",\n"
        "    then use \"x\": \"Country\", \"y\": \"ventas\" (case-sensitive match).\n"
        "  - For pie charts: \"columna\" is the category column, \"valores\" is the numeric column.\n\n"
        "--- VALIDATION — Always verify before saving ---\n"
        "  After building or modifying ui_config.json:\n"
        "  1. Call validate_config() to check all SQL queries execute correctly.\n"
        "  2. Fix any errors reported before telling the user the dashboard is ready.\n"
        "  3. A valid config has 0 structural errors and 0 SQL errors.\n\n"
        "========================================================================\n"
        "KEY RULES\n"
        "========================================================================\n\n"
        "- NEVER hardcode column names. Use names from explore_data() or detect_columns().\n"
        "- create_dashboard() is the primary tool — it starts the server automatically.\n"
        "- Always share the returned URL with the user after creating a dashboard.\n"
        "- The UI auto-refreshes every 3 seconds. No server restart needed for changes.\n"
        "- After create_dashboard(), check quality with get_config(). If poor, enrich it.\n"
        "- Use explore_data() to understand any dataset before building custom charts.\n"
        "- SQL in config runs against DuckDB. Use double-quotes for column names with spaces.\n"
        "- When the user asks a data question, use run_query() or get_kpi() to answer.\n"
        "- A good dashboard has: ≥3 KPIs, ≥2 charts, ≥1 filter, and meaningful labels.\n"
        "- Use multiple modules for complex data (e.g. \"Overview\" + \"Details\" + \"Inventory\").\n"
        "- ⚠️ NEVER put hex colors in chart `color` fields — only in KPI `color` fields.\n"
        "- ⚠️ ALWAYS validate your config with validate_config() before delivering.\n"
    ),
)

CONFIG_PATH = _PROJECT_ROOT / "ui_config.json"

# --------------------------------------------------------------------------- #
# Streamlit Server Management
# --------------------------------------------------------------------------- #

_STREAMLIT_PORT = 8501
_streamlit_process: subprocess.Popen | None = None
_streamlit_started_by_mcp = False  # Track if MCP started it (so we can stop it)


def _find_free_port(start_port: int = 8501, max_attempts: int = 10) -> int:
    """Find an available port starting from the given port."""
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    return start_port  # Fallback to original


def _is_streamlit_running() -> bool:
    """Check if the tracked Streamlit process is still running."""
    if _streamlit_process is None:
        return False
    return _streamlit_process.poll() is None


# --------------------------------------------------------------------------- #
# Streamlit Management Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def start_streamlit(port: int = 8501) -> str:
    """Start the Streamlit dashboard server in the background.

    Launches the Streamlit app so the user can view the dashboard in their
    browser. The server auto-refreshes every 3 seconds when ui_config.json
    changes.

    Args:
        port: Port number for the server (default: 8501).

    Returns:
        The URL to open in the browser and server status.
    """
    global _streamlit_process, _streamlit_started_by_mcp

    # Check if already running
    if _is_streamlit_running():
        return (
            f"⚠️ Streamlit is already running!\n\n"
            f"URL: http://localhost:{_STREAMLIT_PORT}\n\n"
            f"Open this URL in your browser to view the dashboard."
        )

    # Check if port is in use by another process
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", port))
        except OSError:
            return (
                f"⚠️ Port {port} is already in use by another process.\n\n"
                f"Try a different port or stop the existing process first.\n"
                f"You can check with: check_streamlit_status()"
            )

    # Find python executable (prefer venv if available)
    venv_python = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        python_exe = str(venv_python)
    else:
        python_exe = sys.executable  # Use current Python

    streamlit_main = _PROJECT_ROOT / "streamlit_ui" / "main.py"

    # Start Streamlit in background
    try:
        log_file = _PROJECT_ROOT / "streamlit.log"
        with open(log_file, "w") as log:
            _streamlit_process = subprocess.Popen(
                [
                    python_exe, "-m", "streamlit", "run",
                    str(streamlit_main),
                    "--server.port", str(port),
                    "--server.headless", "true",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(_PROJECT_ROOT),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        _streamlit_started_by_mcp = True
        _STREAMLIT_PORT = port

        # Give it a moment to start
        import time
        time.sleep(2)

        if _is_streamlit_running():
            url = f"http://localhost:{port}"
            return (
                f"✅ Streamlit server started successfully!\n\n"
                f"URL: {url}\n\n"
                f"📌 IMPORTANT: Please open this URL in your browser:\n"
                f"  {url}\n\n"
                f"The dashboard will auto-refresh every 3 seconds when the config changes.\n"
                f"Tell the user to open the link above to see their dashboard."
            )
        else:
            return (
                f"❌ Streamlit server failed to start.\n\n"
                f"Check the log file: {log_file}\n"
                f"Error: Process exited immediately."
            )

    except Exception as e:
        return f"❌ Error starting Streamlit: {e}"


@mcp.tool()
def stop_streamlit() -> str:
    """Stop the Streamlit dashboard server.

    Returns:
        Confirmation message.
    """
    global _streamlit_process, _streamlit_started_by_mcp

    if not _is_streamlit_running():
        return "Streamlit server is not running."

    try:
        _streamlit_process.terminate()
        _streamlit_process.wait(timeout=5)
        _streamlit_process = None
        _streamlit_started_by_mcp = False
        return "✅ Streamlit server stopped successfully."
    except subprocess.TimeoutExpired:
        # Force kill if it doesn't stop gracefully
        try:
            _streamlit_process.kill()
            _streamlit_process = None
            _streamlit_started_by_mcp = False
            return "✅ Streamlit server force-stopped."
        except Exception as e:
            return f"Error stopping Streamlit: {e}"
    except Exception as e:
        return f"Error stopping Streamlit: {e}"


@mcp.tool()
def check_streamlit_status() -> str:
    """Check if the Streamlit dashboard server is running.

    Returns:
        Server status and URL if running.
    """
    if _is_streamlit_running():
        return (
            f"✅ Streamlit server is RUNNING.\n\n"
            f"URL: http://localhost:{_STREAMLIT_PORT}\n"
            f"PID: {_streamlit_process.pid if _streamlit_process else 'unknown'}\n"
            f"Started by MCP: {_streamlit_started_by_mcp}"
        )
    else:
        return (
            "❌ Streamlit server is NOT running.\n\n"
            "Start it with: start_streamlit()\n"
            "Or let create_dashboard() start it automatically."
        )


# --------------------------------------------------------------------------- #
# Data Management Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def create_dashboard(file_path: str, dashboard_name: str = "Dashboard") -> str:
    """Create a complete dashboard from a CSV file in one step.

    This is the MAIN entry point for users. It handles the entire workflow:
    uploads the CSV, detects columns, generates KPIs, charts, and filters,
    and saves the configuration. The Streamlit UI will render automatically.

    Args:
        file_path: Absolute path to the CSV/Excel file on disk.
        dashboard_name: Optional title for the dashboard (default: "Dashboard").

    Returns:
        Summary of what was created (KPIs, charts, filters) and confirmation.
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    # Step 1: Determine table name from file stem
    table_name = path.stem.replace(" ", "_").lower()
    if not table_name:
        table_name = "data"

    # Step 2: Upload the CSV
    class _FileWrapper:
        def __init__(self, p: Path):
            self._path = p
            self._name = p.name

        def getvalue(self) -> bytes:
            return self._path.read_bytes()

        @property
        def name(self) -> str:
            return self._name

    wrapper = _FileWrapper(path)
    mensajes = ingestir_tabla(table_name, [wrapper])

    # Close the persistent connection so Streamlit can access the DB
    close_con()

    # Step 3: Read sample data (uses ephemeral connection)
    try:
        df_head = ejecutar(f"SELECT * FROM {table_name} LIMIT 100")
    except Exception as e:
        return f"Error reading data after upload: {e}"

    if df_head.empty:
        return "Error: The uploaded file appears to be empty."

    # Step 4: Generate config automatically
    config = generar_ui_config(df_head, table_name=table_name)
    config["titulo_pagina"] = dashboard_name
    config["brand_name"] = dashboard_name

    # Step 5: Validate and save
    result = actualizar_ui_config(config, CONFIG_PATH)

    # Step 6: Build summary
    n_modulos = len(config.get("modulos", []))
    n_filtros = len(config.get("filtros_globales", []))
    n_mappings = len(config.get("column_mapping", {}))

    # Count KPIs and charts across all modules
    total_kpis = 0
    total_charts = 0
    total_tables = 0
    for mod in config.get("modulos", []):
        total_kpis += len(mod.get("kpis", []))
        total_charts += len(mod.get("graficos", []))
        total_tables += len(mod.get("tablas", []))

    # Step 7: Start Streamlit server automatically
    streamlit_result = start_streamlit()

    # Extract URL from streamlit result
    dashboard_url = f"http://localhost:{_STREAMLIT_PORT}"

    summary = (
        f"✅ Dashboard '{dashboard_name}' created successfully!\n\n"
        f"Data: {path.name} → table '{table_name}' ({len(df_head)} rows sampled)\n"
        f"Columns detected: {n_mappings} mappings\n\n"
        f"Dashboard contents:\n"
        f"  - {n_modulos} module(s)\n"
        f"  - {total_kpis} KPI(s)\n"
        f"  - {total_charts} chart(s)\n"
        f"  - {total_tables} data table(s)\n"
        f"  - {n_filtros} filter(s)\n\n"
        f"{'─' * 50}\n"
        f"🚀 Dashboard is LIVE!\n\n"
        f"📌 OPEN THIS URL IN YOUR BROWSER:\n"
        f"  {dashboard_url}\n\n"
        f"The dashboard auto-refreshes every 3 seconds.\n"
        f"Tell the user: 'Tu dashboard está listo. Ábrelo en: {dashboard_url}'\n"
        f"{'─' * 50}"
    )

    return summary


@mcp.tool()
def upload_csv(file_path: str, table_name: str = "data") -> str:
    """Upload a CSV/Excel file to the dashboard database.

    The file will be ingested into a DuckDB table with the given name.
    The MCP agent decides the table name — no auto-classification.

    Args:
        file_path: Absolute path to the CSV/Excel file on disk.
        table_name: Target table name in DuckDB (default: "data").

    Returns:
        Status message with ingestion result.
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    class _FileWrapper:
        def __init__(self, p: Path):
            self._path = p
            self._name = p.name

        def getvalue(self) -> bytes:
            return self._path.read_bytes()

        @property
        def name(self) -> str:
            return self._name

    wrapper = _FileWrapper(path)
    mensajes = ingestir_tabla(table_name, [wrapper])

    # Close the persistent connection so Streamlit can access the DB
    close_con()

    tables = tablas_disponibles()
    return (
        f"File '{path.name}' uploaded to table '{table_name}'.\n"
        f"Results:\n" + "\n".join(f"  - {m}" for m in mensajes) + "\n"
        f"Active tables:\n" + "\n".join(f"  - {t}" for t in tables)
    )


@mcp.tool()
def upload_multiple_csvs(file_paths: list[str], table_name: str = "data") -> str:
    """Upload multiple CSV/Excel files at once into the same table.

    Args:
        file_paths: List of absolute paths to CSV/Excel files.
        table_name: Target table name in DuckDB (default: "data").

    Returns:
        Status message with all upload results.
    """

    class _FileWrapper:
        def __init__(self, p: Path):
            self._path = p
            self._name = p.name

        def getvalue(self) -> bytes:
            return self._path.read_bytes()

        @property
        def name(self) -> str:
            return self._name

    wrappers = []
    errors = []
    for fp in file_paths:
        p = Path(fp)
        if p.exists():
            wrappers.append(_FileWrapper(p))
        else:
            errors.append(f"Not found: {fp}")

    mensajes = []
    if wrappers:
        mensajes = ingestir_tabla(table_name, wrappers)

    # Close the persistent connection so Streamlit can access the DB
    close_con()

    tables = tablas_disponibles()

    result = "Upload complete.\n"
    if errors:
        result += f"Errors:\n" + "\n".join(f"  - {e}" for e in errors) + "\n"
    if mensajes:
        result += f"Results:\n" + "\n".join(f"  - {m}" for m in mensajes) + "\n"
    result += f"Active tables:\n" + "\n".join(f"  - {t}" for t in tables)
    return result


@mcp.tool()
def list_tables() -> str:
    """List all tables currently loaded in the database.

    Returns:
        List of tables with their source file names and row counts.
    """
    tables = tablas_disponibles()
    if not tables:
        return "No data loaded. Upload CSV files first."

    result = "Loaded tables:\n"
    for tabla in sorted(tables):
        file_name = archivo_en_uso(tabla)
        try:
            df = ejecutar(f"SELECT COUNT(*) AS n FROM {tabla}")
            count = int(df["n"].iloc[0]) if not df.empty else 0
        except Exception:
            count = "?"
        result += f"  - {tabla}: {file_name} ({count} rows)\n"

    return result.rstrip()


@mcp.tool()
def get_table_columns(table_name: str) -> str:
    """Get the column names and types for a specific table.

    Args:
        table_name: Table name in DuckDB (e.g. "sales", "my_data").

    Returns:
        Column names with their data types.
    """
    if not tabla_existe(table_name):
        available = tablas_disponibles()
        if not available:
            return "No tables loaded. Upload a file first."
        return f"Table '{table_name}' not found. Available tables: {', '.join(available)}"

    try:
        df = ejecutar(f"DESCRIBE {table_name}")
        columns = []
        for _, row in df.iterrows():
            columns.append(f"  - {row['column_name']}: {row['column_type']}")
        return f"Columns in {table_name}:\n" + "\n".join(columns)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def clear_data() -> str:
    """Clear all data from the database and reset the dashboard.

    Returns:
        Confirmation message.
    """
    limpiar_datos()
    # Also remove config file so it gets regenerated
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    return "All data cleared. Database and config reset."


# --------------------------------------------------------------------------- #
# Configuration Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def generate_config() -> str:
    """Auto-generate the UI configuration based on loaded data.

    Analyzes the first 100 rows of ALL loaded tables, detects column roles using
    synonym matching, and generates a complete ui_config.json with:
    - column_mapping (role → physical column)
    - filtros_globales (filter definitions)
    - modulos (KPIs, charts, tables with SQL queries)

    The table name(s) discovered from the database are used in all generated SQL.

    Returns:
        The generated JSON configuration as a string.
    """
    if not hay_datos():
        return "No data loaded. Upload CSV files first."

    # Read sample data from ALL available tables
    all_dfs = []
    tables = tablas_disponibles()
    for tabla in tables:
        try:
            df = ejecutar(f"SELECT * FROM {tabla} LIMIT 100")
            all_dfs.append(df)
        except Exception:
            pass

    if not all_dfs:
        return "Could not read sample data."

    df_head = pd.concat(all_dfs, ignore_index=True)
    # Use the first available table name for SQL generation
    table_name = tables[0] if tables else "data"
    config = generar_ui_config(df_head, table_name=table_name)

    # Validate and save via tools.py (ensures structure is correct)
    result = actualizar_ui_config(config, CONFIG_PATH)

    # Summary
    n_modulos = len(config.get("modulos", []))
    n_filtros = len(config.get("filtros_globales", []))
    n_mappings = len(config.get("column_mapping", {}))

    return (
        f"Config generated and saved to {CONFIG_PATH.name}.\n"
        f"  - {n_mappings} column mappings\n"
        f"  - {n_filtros} global filters\n"
        f"  - {n_modulos} modules (with KPIs, charts, tables)\n\n"
        f"Full JSON:\n{json.dumps(config, indent=2, ensure_ascii=False)}"
    )


@mcp.tool()
def get_config() -> str:
    """Read the current UI configuration file (alias for load_config).

    Returns:
        The current ui_config.json content as a formatted JSON string.
    """
    return load_config()


@mcp.tool()
def update_config(json_string: str) -> str:
    """Update the UI configuration file with validated JSON.

    This tool validates the complete ui_config.json structure before saving:
    - Checks required keys: modulos, filtros_globales, column_mapping
    - Validates each module has id, nombre, and proper kpis/graficos/tablas
    - Validates each KPI has sql and label
    - Validates each chart has sql, tipo, and titulo
    - Validates each filter has nombre, columna, and tabla
    - Validates all SQL queries for syntax errors
    - Auto-fills missing optional fields (brand_name, footer, empty_state, etc.)
    - Creates a backup of the previous config (.json.bak)

    ⚠️ BEFORE calling this tool, you MUST:
    1. Review your JSON carefully — especially chart `color` fields (column name, NOT hex).
    2. Ensure all SQL queries use the correct table name and column names.
    3. After saving, call validate_config() to verify all queries execute correctly.
    4. Fix any errors reported by validate_config() before telling the user it's ready.

    Args:
        json_string: Valid JSON string with complete ui_config.json structure.
        See the expected structure in the tool documentation.

    Returns:
        Validation result and save confirmation with summary counts.
    """
    try:
        config = json.loads(json_string)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    return actualizar_ui_config(config, CONFIG_PATH)


@mcp.tool()
def load_config() -> str:
    """Load the current ui_config.json from disk.

    Returns:
        The current config as a formatted JSON string, or error if not found.
    """
    config = cargar_config(CONFIG_PATH)
    if not config:
        return "No config file found. Run generate_config or update_config first."
    return json.dumps(config, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Query Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def run_query(sql: str) -> str:
    """Execute a SQL query against the DuckDB database.

    Args:
        sql: SQL query string (e.g. "SELECT branch, SUM(total_usd) FROM sales GROUP BY branch").

    Returns:
        Query results as a formatted table (CSV-like) or error message.
    """
    if not hay_datos():
        return "No data loaded. Upload CSV files first."

    try:
        df = ejecutar(sql)
    except Exception as e:
        return f"Query error: {e}"

    if df.empty:
        return f"Query error: {ultimo_error()}" if ultimo_error() else "Query returned no results."

    # Format as CSV for readability
    csv_output = df.to_csv(index=False)
    n_rows = len(df)
    n_cols = len(df.columns)

    return f"Query returned {n_rows} rows × {n_cols} columns:\n\n{csv_output}"


@mcp.tool()
def run_query_with_filters(
    sql: str,
    filters_json: str
) -> str:
    """Execute a SQL query with dynamic filters from the config.

    Args:
        sql: SQL query string.
        filters_json: JSON string with filter config and values, e.g.:
            {
                "filtros_config": [{"nombre": "branch", "columna": "branch", "tipo": "select"}],
                "filtros_valores": {"branch": "A"}
            }

    Returns:
        Query results as CSV.
    """
    if not hay_datos():
        return "No data loaded. Upload CSV files first."

    try:
        filters_data = json.loads(filters_json)
        filtros_config = filters_data.get("filtros_config", [])
        filtros_valores = filters_data.get("filtros_valores", {})
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    query_config = {"sql": sql}
    try:
        df = ejecutar_query(query_config, filtros_config, filtros_valores)
    except Exception as e:
        return f"Query error: {e}"

    if df.empty:
        return f"Query error: {ultimo_error()}" if ultimo_error() else "Query returned no results."

    csv_output = df.to_csv(index=False)
    return f"Query returned {len(df)} rows × {len(df.columns)} columns:\n\n{csv_output}"


@mcp.tool()
def get_kpi(kpi_json: str) -> str:
    """Execute a KPI query and return a single value.

    Args:
        kpi_json: JSON string with KPI config, e.g.:
            {
                "sql": "SELECT COALESCE(SUM(total_usd), 0) AS v FROM sales",
                "label": "Total Sales",
                "formato": "money"
            }

    Returns:
        The KPI value formatted as a string.
    """
    if not hay_datos():
        return "No data loaded."

    try:
        kpi_config = json.loads(kpi_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    try:
        errores_antes = error_seq()
        valor = ejecutar_kpi(kpi_config)
        if error_seq() != errores_antes:
            return f"KPI error: {ultimo_error()}"
        label = kpi_config.get("label", "KPI")
        formato = kpi_config.get("formato", "number")

        if formato == "money":
            return f"{label}: ${valor:,.2f}"
        elif formato == "percent":
            return f"{label}: {valor:.1f}%"
        elif formato == "int":
            return f"{label}: {valor:,}"
        elif formato == "str":
            return f"{label}: {valor}"
        else:
            return f"{label}: {valor}"
    except Exception as e:
        return f"KPI error: {e}"


# --------------------------------------------------------------------------- #
# Filter Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_filter_options(filter_json: str) -> str:
    """Get distinct values for a filter column.

    Args:
        filter_json: JSON string with filter config, e.g.:
            {"nombre": "branch", "columna": "branch", "tabla": "sales", "tipo": "select"}

    Returns:
        List of distinct values.
    """
    if not hay_datos():
        return "No data loaded."

    try:
        filtro_config = json.loads(filter_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    try:
        options = obtener_opciones_filtro(filtro_config)
        nombre = filtro_config.get("nombre", "filter")
        return f"Options for '{nombre}' ({len(options)} values):\n" + "\n".join(f"  - {o}" for o in options)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_date_range(filter_json: str) -> str:
    """Get the min/max date range for a date column.

    Args:
        filter_json: JSON string with filter config, e.g.:
            {"nombre": "date_range", "columna": "date", "tabla": "sales", "tipo": "date_range"}

    Returns:
        Date range as a string.
    """
    if not hay_datos():
        return "No data loaded."

    try:
        filtro_config = json.loads(filter_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    try:
        min_date, max_date = obtener_rango_fechas(filtro_config)
        return f"Date range: {min_date} to {max_date}"
    except Exception as e:
        return f"Error: {e}"


# --------------------------------------------------------------------------- #
# Column Detection Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def detect_columns(table_name: str) -> str:
    """Detect which columns map to which roles for a loaded table.

    Uses the _ROLES synonym dictionary to match physical CSV columns to
    logical roles (e.g. "branch" → "sucursal", "total_usd" → "monto").
    The MCP agent can use this to understand the data before generating config.

    Args:
        table_name: Table name in DuckDB.

    Returns:
        Column role mapping as a formatted string.
    """
    if not tabla_existe(table_name):
        available = tablas_disponibles()
        if not available:
            return "No tables loaded."
        return f"Table '{table_name}' not found. Available: {', '.join(available)}"

    try:
        df = ejecutar(f"SELECT * FROM {table_name} LIMIT 100")
    except Exception as e:
        return f"Error reading table: {e}"

    # Try all known role sets to find the best match
    best_type = None
    best_mapping = {}
    for tipo in _ROLES:
        mapping = _detectar_columnas_fisicas(df, tipo)
        if len(mapping) > len(best_mapping):
            best_mapping = mapping
            best_type = tipo

    if not best_mapping:
        return f"No columns detected for '{table_name}'."

    lines = [f"Detected columns for '{table_name}' (matched as '{best_type}'):"]
    for rol, col in best_mapping.items():
        lines.append(f"  - {rol} → {col}")

    return "\n".join(lines)


@mcp.tool()
def get_available_roles() -> str:
    """List all available column roles and their synonyms.

    Returns:
        All role definitions with their synonym lists.
    """
    lines = ["Available column roles and synonyms:"]
    for tipo, roles in _ROLES.items():
        lines.append(f"\n  {tipo}:")
        for rol, synonyms in roles.items():
            lines.append(f"    {rol}: {', '.join(synonyms[:5])}{'...' if len(synonyms) > 5 else ''}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Validation Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def validate_config() -> str:
    """Validate all SQL queries in the current ui_config.json against the database.

    This tool checks:
    - JSON structure validity (required keys, types)
    - SQL syntax for every KPI, chart, and table query
    - Executes each query to verify it returns results
    - Reports execution time for each query

    Use this AFTER generate_config() or update_config() to verify the dashboard
    will render correctly before showing it to the user.

    Returns:
        A detailed validation report showing pass/fail status for each query.
    """
    config = cargar_config(CONFIG_PATH)
    if not config:
        return "No config file found. Run generate_config or update_config first."

    import time as _time

    lines = ["=== Config Validation Report ===", ""]

    # 1. Structure validation
    from core.tools import _validar_config, _validar_sql_en_config
    struct_errors = _validar_config(config)
    sql_errors = _validar_sql_en_config(config)

    if struct_errors:
        lines.append("❌ Structure errors:")
        for e in struct_errors:
            lines.append(f"   - {e}")
        lines.append("")

    if sql_errors:
        lines.append("❌ SQL syntax errors:")
        for e in sql_errors:
            lines.append(f"   - {e}")
        lines.append("")

    # 2. Execute each query and report
    lines.append("--- Query Execution Results ---")
    total = 0
    passed = 0
    failed = 0

    for mod in config.get("modulos", []):
        mod_name = mod.get("nombre", "Unknown")
        lines.append(f"\n  Module: {mod_name}")

        # KPIs
        for kpi in mod.get("kpis", []):
            label = kpi.get("label", "?")
            sql = kpi.get("sql", "")
            total += 1
            try:
                start = _time.time()
                df = ejecutar(sql)
                elapsed = _time.time() - start
                if not df.empty:
                    val = df.iloc[0, 0]
                    lines.append(f"  ✓ KPI '{label}': {val} ({elapsed:.3f}s)")
                    passed += 1
                else:
                    lines.append(f"  ⚠ KPI '{label}': empty result ({elapsed:.3f}s)")
                    failed += 1
            except Exception as e:
                lines.append(f"  ✗ KPI '{label}': {e}")
                failed += 1

        # Charts
        for ch in mod.get("graficos", []):
            titulo = ch.get("titulo", "?")
            sql = ch.get("sql", "")
            total += 1
            try:
                start = _time.time()
                df = ejecutar(sql)
                elapsed = _time.time() - start
                if not df.empty:
                    lines.append(f"  ✓ Chart '{titulo}': {len(df)} rows ({elapsed:.3f}s)")
                    passed += 1
                else:
                    lines.append(f"  ⚠ Chart '{titulo}': empty result ({elapsed:.3f}s)")
                    failed += 1
            except Exception as e:
                lines.append(f"  ✗ Chart '{titulo}': {e}")
                failed += 1

        # Tables
        for tbl in mod.get("tablas", []):
            titulo = tbl.get("titulo", "?")
            sql = tbl.get("sql", "")
            total += 1
            try:
                start = _time.time()
                df = ejecutar(sql)
                elapsed = _time.time() - start
                if not df.empty:
                    lines.append(f"  ✓ Table '{titulo}': {len(df)} rows ({elapsed:.3f}s)")
                    passed += 1
                else:
                    lines.append(f"  ⚠ Table '{titulo}': empty result ({elapsed:.3f}s)")
                    failed += 1
            except Exception as e:
                lines.append(f"  ✗ Table '{titulo}': {e}")
                failed += 1

    # Summary
    lines.append(f"\n=== Summary ===")
    lines.append(f"  Total queries: {total}")
    lines.append(f"  Passed: {passed} ✓")
    lines.append(f"  Failed/Empty: {failed} {'✗' if failed else ''}")
    lines.append(f"  Structure errors: {len(struct_errors)}")
    lines.append(f"  SQL syntax errors: {len(sql_errors)}")

    if failed == 0 and not struct_errors and not sql_errors:
        lines.append(f"\n✅ All queries validated successfully!")
    else:
        lines.append(f"\n⚠️  Some issues found — review the report above.")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Preview Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def preview_table(table_name: str, limit: int = 10) -> str:
    """Preview the first N rows of a table.

    Args:
        table_name: Table name in DuckDB.
        limit: Number of rows to preview (default: 10).

    Returns:
        Table data as CSV.
    """
    if not tabla_existe(table_name):
        available = tablas_disponibles()
        if not available:
            return "No tables loaded."
        return f"Table '{table_name}' not found. Available: {', '.join(available)}"

    try:
        df = ejecutar(f"SELECT * FROM {table_name} LIMIT {int(limit)}")
        csv_output = df.to_csv(index=False)
        return f"First {min(limit, len(df))} rows of '{table_name}':\n\n{csv_output}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def explore_data(table_name: str) -> str:
    """Explore a table's data: column types, statistics, and chart recommendations.

    This is the key tool for designing a good dashboard. It returns:
    - Total rows and columns
    - Each column's type, unique values, null count, and sample values
    - Classification: which columns are categorical, numeric, or date
    - Chart recommendations based on column combinations
    - Suggested KPIs based on numeric columns

    Use this AFTER upload_csv to understand the data before calling
    generate_config() or building custom charts.

    Args:
        table_name: Table name in DuckDB.

    Returns:
        Detailed data exploration report with recommendations.
    """
    if not tabla_existe(table_name):
        available = tablas_disponibles()
        if not available:
            return "No tables loaded."
        return f"Table '{table_name}' not found. Available: {', '.join(available)}"

    try:
        df = ejecutar(f"SELECT * FROM {table_name} LIMIT 100")
    except Exception as e:
        return f"Error reading table: {e}"

    if df.empty:
        return "Table is empty."

    # Row count
    try:
        count_df = ejecutar(f"SELECT COUNT(*) AS n FROM {table_name}")
        total_rows = int(count_df["n"].iloc[0]) if not count_df.empty else "?"
    except Exception:
        total_rows = "?"

    # Classify columns
    classified = _clasificar_columnas(df)
    cat_cols = classified["categorical"]
    num_cols = classified["numeric"]
    date_cols = classified["date"]
    high_card = classified["high_cardinality"]

    lines = [
        f"=== Data Exploration: '{table_name}' ===",
        f"",
        f"Shape: {total_rows} rows × {len(df.columns)} columns",
        f"",
        f"--- Column Classification ---",
        f"  Categorical ({len(cat_cols)}): {', '.join(cat_cols) if cat_cols else '(none)'}",
        f"  Numeric ({len(num_cols)}): {', '.join(num_cols) if num_cols else '(none)'}",
        f"  Date ({len(date_cols)}): {', '.join(date_cols) if date_cols else '(none)'}",
        f"  High cardinality ({len(high_card)}): {', '.join(high_card) if high_card else '(none)'}",
        f"",
        f"--- Column Details ---",
    ]

    for col in df.columns:
        dtype = str(df[col].dtype)
        unique_count = df[col].nunique()
        null_count = int(df[col].isnull().sum())
        sample_vals = df[col].dropna().head(3).tolist()

        lines.append(f"  {col}:")
        lines.append(f"    Type: {dtype}")
        lines.append(f"    Unique values: {unique_count}")
        lines.append(f"    Nulls: {null_count}")
        lines.append(f"    Sample: {sample_vals}")

        # Stats for numeric columns
        if col in num_cols:
            mean_val = df[col].mean()
            min_val = df[col].min()
            max_val = df[col].max()
            lines.append(f"    Stats: min={min_val:.2f}, max={max_val:.2f}, avg={mean_val:.2f}")

        lines.append("")

    # Recommendations
    lines.append("--- Dashboard Recommendations ---")

    if num_cols:
        lines.append(f"  Suggested KPIs:")
        for nc in num_cols:
            label = nc.replace("_", " ").title()
            lines.append(f"    - Total {label}: SUM({nc})")
            lines.append(f"    - Average {label}: AVG({nc})")
        lines.append(f"    - Total Records: COUNT(*)")

    if cat_cols and num_cols:
        lines.append(f"  Suggested Charts:")
        for cc in cat_cols[:3]:
            for nc in num_cols[:2]:
                cat_label = cc.replace("_", " ").title()
                num_label = nc.replace("_", " ").title()
                lines.append(f"    - Bar: {num_label} by {cat_label}")
                if df[cc].nunique() <= 8:
                    lines.append(f"    - Pie: Share of {num_label} by {cat_label}")

    if date_cols and num_cols:
        lines.append(f"  Suggested Charts:")
        for dc in date_cols:
            for nc in num_cols[:2]:
                date_label = dc.replace("_", " ").title()
                num_label = nc.replace("_", " ").title()
                lines.append(f"    - Line: {num_label} over {date_label}")

    if cat_cols:
        lines.append(f"  Suggested Filters:")
        for cc in cat_cols:
            lines.append(f"    - {cc} (select/multiselect)")
    if date_cols:
        for dc in date_cols:
            lines.append(f"    - {dc} (date range)")

    lines.append("")
    lines.append("--- Next Steps ---")
    lines.append("  1. Review the recommendations above")
    lines.append("  2. Call generate_config() to auto-create the dashboard")
    lines.append("  3. Or use build_chart_config/build_kpi_config for custom charts")
    lines.append("  4. Call update_config() to save your custom configuration")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Chart Builder Tools — for the MCP agent to know how to build charts
# --------------------------------------------------------------------------- #


@mcp.tool()
def list_chart_types() -> str:
    """List all available chart types with descriptions and usage guidance.

    Use this to understand what chart types the dashboard supports and when
    to use each one.

    Returns:
        Human-readable list of chart types with examples.
    """
    return listar_tipos_grafica()


@mcp.tool()
def recommend_chart(sql: str) -> str:
    """Recommend chart types based on the data returned by a SQL query.

    Execute the SQL, analyze the resulting DataFrame columns, and suggest
    the most appropriate chart types with their config keys.

    Args:
        sql: SQL query to execute against DuckDB.

    Returns:
        List of chart recommendations with reasons and config examples.
    """
    if not hay_datos():
        return "No data loaded. Upload a CSV first."

    try:
        df = ejecutar(sql)
    except Exception as e:
        return f"SQL error: {e}"

    if df.empty:
        return f"Query error: {ultimo_error()}" if ultimo_error() else "Query returned no data."

    recommendations = recomendar_grafica(df, sql)
    if not recommendations:
        return f"No chart recommendations for this data shape. Columns: {list(df.columns)}"

    lines = [f"Query returned {len(df)} rows, {len(df.columns)} columns: {list(df.columns)}\n"]
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"  {i}. {rec['tipo'].upper()}")
        lines.append(f"     Reason: {rec['razon']}")
        lines.append(f"     Config: {json.dumps(rec['config'])}")

    return "\n".join(lines)


@mcp.tool()
def build_chart_config(chart_json: str) -> str:
    """Build a complete chart config dict for ui_config.json.

    ⚠️ IMPORTANT: The `color` field in charts is a COLUMN NAME for grouping,
    NOT a hex color. If you want a single-color chart, omit `color` entirely.
    Hex colors (like "#246bfd") are only for KPI cards, not charts.

    Args:
        chart_json: JSON string with chart parameters:
            {
                "tipo": "bar",
                "sql": "SELECT branch, SUM(total_usd) AS Sales FROM sales GROUP BY branch",
                "titulo": "Sales by Branch",
                "x": "branch",
                "y": "Sales",
                "alto": 380
            }
        Optional fields:
            "color": Column name for grouping (e.g. "Country"), NOT a hex color.
            "sub": Description text below the chart title.
            "icono": Material icon name.
            "col_izq": Width ratio for side-by-side charts (0.5 = half width).

    Returns:
        Complete chart config dict as JSON string.
    """
    try:
        params = json.loads(chart_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    try:
        config = construir_config_grafico(**params)
        return json.dumps(config, indent=2)
    except Exception as e:
        return f"Error building chart config: {e}"


@mcp.tool()
def build_kpi_config(kpi_json: str) -> str:
    """Build a complete KPI config dict for ui_config.json.

    Note: The `color` field in KPIs IS a hex color for the card background
    (e.g. "#246bfd"). This is different from charts where `color` is a column name.

    Args:
        kpi_json: JSON string with KPI parameters:
            {
                "sql": "SELECT SUM(total_usd) FROM sales",
                "label": "Total Sales",
                "icono": "payments",
                "formato": "money",
                "color": "#246bfd"
            }
        The SQL must return a single value in a column named "v".

    Returns:
        Complete KPI config dict as JSON string.
    """
    try:
        params = json.loads(kpi_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    try:
        config = construir_config_kpi(**params)
        return json.dumps(config, indent=2)
    except Exception as e:
        return f"Error building KPI config: {e}"


@mcp.tool()
def build_filter_config(filter_json: str) -> str:
    """Build a complete filter config dict for ui_config.json.

    Args:
        filter_json: JSON string with filter parameters:
            {
                "nombre": "branch",
                "columna": "branch",
                "tabla": "sales",
                "tipo": "select",
                "etiqueta": "Branch"
            }

    Returns:
        Complete filter config dict as JSON string.
    """
    try:
        params = json.loads(filter_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    try:
        config = construir_config_filtro(**params)
        return json.dumps(config, indent=2)
    except Exception as e:
        return f"Error building filter config: {e}"


@mcp.tool()
def build_module_config(module_json: str) -> str:
    """Build a complete module config dict for ui_config.json.

    Args:
        module_json: JSON string with module parameters:
            {
                "modulo_id": "dashboard",
                "nombre": "Executive Overview",
                "icono": "📊",
                "material_icon": "dashboard",
                "descripcion": "Business summary",
                "kpis": [...],
                "graficos": [...]
            }

    Returns:
        Complete module config dict as JSON string.
    """
    try:
        params = json.loads(module_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    try:
        config = construir_config_modulo(**params)
        return json.dumps(config, indent=2)
    except Exception as e:
        return f"Error building module config: {e}"


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

def main():
    """Entry point for the agentui-mcp command."""
    print("Starting MCP server (stdio transport)...", flush=True)
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()