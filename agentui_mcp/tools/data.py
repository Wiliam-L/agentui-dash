"""Data management MCP tools.

Tools: create_dashboard, upload_csv, upload_multiple_csvs,
       list_tables, get_table_columns, clear_data
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastmcp import FastMCP

from agentui_mcp.utils import CONFIG_PATH, FileWrapper

_logger = logging.getLogger("mcp.data")

from app_base.core.data import (
    close_con,
    ingest_table,
    clear_data as _clear_data,
    has_data,
    table_exists,
    available_tables,
    file_in_use,
    run_query as _run_query,
)
from app_base.core.inference import generate_ui_config
from app_base.core.tools import update_ui_config as _update_ui_config


def register_data_tools(mcp: FastMCP) -> None:
    """Register data management tools on the MCP server."""

    @mcp.tool()
    def create_dashboard(file_path: str, dashboard_name: str = "Dashboard") -> str:
        """Create a complete dashboard from a CSV file in one step.

        This is the MAIN entry point for users. It handles the entire workflow:
        uploads the CSV, detects columns, generates KPIs, charts, and filters,
        and saves the configuration. The Streamlit UI (already running) will
        auto-refresh to display the new dashboard.

        Args:
            file_path: Absolute path to the CSV/Excel file on disk.
            dashboard_name: Optional title for the dashboard (default: "Dashboard").

        Returns:
            Summary of what was created (KPIs, charts, filters) and the dashboard URL.
        """
        from agentui_mcp.utils import get_streamlit_port

        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"

        # Step 1: Determine table name from file stem
        table_name = path.stem.replace(" ", "_").lower()
        if not table_name:
            table_name = "data"

        # Step 2: Upload the CSV
        wrapper = FileWrapper(path)
        ingest_table(table_name, [wrapper])
        close_con()

        # Step 3: Read sample data
        try:
            df_head = _run_query(f"SELECT * FROM {table_name} LIMIT 100")
        except Exception as e:
            return f"Error reading data after upload: {e}"

        if df_head.empty:
            return "Error: The uploaded file appears to be empty."

        # Step 4: Generate config automatically
        config = generate_ui_config(df_head, table_name=table_name)
        config["titulo_pagina"] = dashboard_name
        config["brand_name"] = dashboard_name

        _logger.info(f"Generated config with {len(config.get('modulos', []))} modules, saving to {CONFIG_PATH}")

        # Step 5: Validate and save
        result = _update_ui_config(config, CONFIG_PATH)
        _logger.info(f"_update_ui_config result: {result[:200]}")

        # Check for validation errors first (these prevent the file from being saved)
        if result.startswith("Validation failed") or result.startswith("SQL validation failed"):
            _logger.error(f"Config validation failed: {result}")
            return (
                "❌ Error: Failed to save dashboard config. The generated SQL or structure is invalid.\n\n"
                f"Details:\n{result}\n\n"
                "Please try again with a different file or check the data structure."
            )

        # Check if config file was actually created (catches silent write failures)
        if not CONFIG_PATH.exists():
            _logger.error(f"Config file was NOT created at {CONFIG_PATH} after _update_ui_config!")
            return (
                "❌ Error: Dashboard config was not saved. The file was not created.\n\n"
                f"Expected path: {CONFIG_PATH}\n"
                f"Result message: {result}\n\n"
                "This may be a permissions issue. Please check that the application has write access to the config directory."
            )

        # Step 6: Build summary
        n_modules = len(config.get("modulos", []))
        n_filters = len(config.get("filtros_globales", []))
        n_mappings = len(config.get("column_mapping", {}))
        total_kpis = 0
        total_charts = 0
        total_tables = 0
        for mod in config.get("modulos", []):
            total_kpis += len(mod.get("kpis", []))
            total_charts += len(mod.get("graficos", []))
            total_tables += len(mod.get("tablas", []))

        # Streamlit is already running from MCP startup — just return the URL
        dashboard_url = f"http://localhost:{get_streamlit_port()}"

        summary = (
            f"✅ Dashboard '{dashboard_name}' created successfully!\n\n"
            f"Data: {path.name} → table '{table_name}' ({len(df_head)} rows sampled)\n"
            f"Columns detected: {n_mappings} mappings\n\n"
            f"Dashboard contents:\n"
            f"  - {n_modules} module(s)\n"
            f"  - {total_kpis} KPI(s)\n"
            f"  - {total_charts} chart(s)\n"
            f"  - {total_tables} data table(s)\n"
            f"  - {n_filters} filter(s)\n\n"
            f"{'─' * 50}\n"
            f"🚀 Dashboard is LIVE!\n\n"
            f"📌 OPEN THIS URL IN YOUR BROWSER:\n"
            f"  {dashboard_url}\n\n"
            f"The dashboard auto-refreshes every 3 seconds.\n"
            f"Tell the user: 'Your dashboard is ready. Open it at: {dashboard_url}'\n"
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

        wrapper = FileWrapper(path)
        messages = ingest_table(table_name, [wrapper])
        close_con()

        tables = available_tables()
        return (
            f"File '{path.name}' uploaded to table '{table_name}'.\n"
            f"Results:\n" + "\n".join(f"  - {m}" for m in messages) + "\n"
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
        wrappers = []
        errors = []
        for fp in file_paths:
            p = Path(fp)
            if p.exists():
                wrappers.append(FileWrapper(p))
            else:
                errors.append(f"Not found: {fp}")

        messages = []
        if wrappers:
            messages = ingest_table(table_name, wrappers)

        close_con()
        tables = available_tables()

        result = "Upload complete.\n"
        if errors:
            result += f"Errors:\n" + "\n".join(f"  - {e}" for e in errors) + "\n"
        if messages:
            result += f"Results:\n" + "\n".join(f"  - {m}" for m in messages) + "\n"
        result += f"Active tables:\n" + "\n".join(f"  - {t}" for t in tables)
        return result

    @mcp.tool()
    def list_tables() -> str:
        """List all tables currently loaded in the database.

        Returns:
            List of tables with their source file names and row counts.
        """
        tables = available_tables()
        if not tables:
            return "No data loaded. Upload CSV files first."

        result = "Loaded tables:\n"
        for tbl in sorted(tables):
            file_name = file_in_use(tbl)
            try:
                df = _run_query(f"SELECT COUNT(*) AS n FROM {tbl}")
                count = int(df["n"].iloc[0]) if not df.empty else 0
            except Exception:
                count = "?"
            result += f"  - {tbl}: {file_name} ({count} rows)\n"

        return result.rstrip()

    @mcp.tool()
    def get_table_columns(table_name: str) -> str:
        """Get the column names and types for a specific table.

        Args:
            table_name: Table name in DuckDB (e.g. "sales", "my_data").

        Returns:
            Column names with their data types.
        """
        if not table_exists(table_name):
            available = available_tables()
            if not available:
                return "No tables loaded. Upload a file first."
            return f"Table '{table_name}' not found. Available tables: {', '.join(available)}"

        try:
            df = _run_query(f"DESCRIBE {table_name}")
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
        _clear_data()
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        return "All data cleared. Database and config reset."
