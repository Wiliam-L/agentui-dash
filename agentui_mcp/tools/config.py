"""Configuration MCP tools.

Tools: generate_config, get_config, update_config, load_config
"""
from __future__ import annotations

import json
from pathlib import Path

from fastmcp import FastMCP
import pandas as pd

from agentui_mcp.utils import CONFIG_PATH

from app_base.core.data import (
    has_data,
    available_tables,
    run_query as _run_query,
)
from app_base.core.inference import generate_ui_config
from app_base.core.tools import (
    update_ui_config as _update_ui_config,
    load_config as _load_config,
)


def register_config_tools(mcp: FastMCP) -> None:
    """Register configuration tools on the MCP server."""

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
        if not has_data():
            return "No data loaded. Upload CSV files first."

        all_dfs = []
        tables = available_tables()
        for tbl in tables:
            try:
                df = _run_query(f"SELECT * FROM {tbl} LIMIT 100")
                all_dfs.append(df)
            except Exception:
                pass

        if not all_dfs:
            return "Could not read sample data."

        df_head = pd.concat(all_dfs, ignore_index=True)
        table_name = tables[0] if tables else "data"
        config = generate_ui_config(df_head, table_name=table_name)

        result = _update_ui_config(config, CONFIG_PATH)

        n_modules = len(config.get("modulos", []))
        n_filters = len(config.get("filtros_globales", []))
        n_mappings = len(config.get("column_mapping", {}))

        return (
            f"Config generated and saved to {CONFIG_PATH.name}.\n"
            f"  - {n_mappings} column mappings\n"
            f"  - {n_filters} global filters\n"
            f"  - {n_modules} modules (with KPIs, charts, tables)\n\n"
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

        Returns:
            Validation result and save confirmation with summary counts.
        """
        try:
            config = json.loads(json_string)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        return _update_ui_config(config, CONFIG_PATH)

    @mcp.tool()
    def load_config() -> str:
        """Load the current ui_config.json from disk.

        Returns:
            The current config as a formatted JSON string, or error if not found.
        """
        config = _load_config(CONFIG_PATH)
        if not config:
            return "No config file found. Run generate_config or update_config first."
        return json.dumps(config, indent=2, ensure_ascii=False)
