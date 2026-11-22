"""Chart builder MCP tools.

Tools: list_chart_types, recommend_chart, build_chart_config,
       build_kpi_config, build_filter_config, build_module_config
"""
from __future__ import annotations

import json

from fastmcp import FastMCP

from app_base.core.data import (
    has_data,
    run_query as _run_query,
    last_error,
)
from app_base.core.chart_builder import (
    recommend_chart as _recommend_chart,
    build_chart_config as _build_chart_config,
    build_kpi_config as _build_kpi_config,
    build_filter_config as _build_filter_config,
    build_module_config as _build_module_config,
    list_chart_types as _list_chart_types,
)


def register_chart_builder_tools(mcp: FastMCP) -> None:
    """Register chart builder tools on the MCP server."""

    @mcp.tool()
    def list_chart_types() -> str:
        """List all available chart types with descriptions and usage guidance.

        Use this to understand what chart types the dashboard supports and when
        to use each one.

        Returns:
            Human-readable list of chart types with examples.
        """
        return _list_chart_types()

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
        if not has_data():
            return "No data loaded. Upload a CSV first."

        try:
            df = _run_query(sql)
        except Exception as e:
            return f"SQL error: {e}"

        if df.empty:
            return f"Query error: {last_error()}" if last_error() else "Query returned no data."

        recommendations = _recommend_chart(df, sql)
        if not recommendations:
            return f"No chart recommendations for this data shape. Columns: {list(df.columns)}"

        lines = [
            f"Query returned {len(df)} rows, {len(df.columns)} columns: {list(df.columns)}\n"
        ]
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
            config = _build_chart_config(**params)
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
            config = _build_kpi_config(**params)
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
            config = _build_filter_config(**params)
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
            config = _build_module_config(**params)
            return json.dumps(config, indent=2)
        except Exception as e:
            return f"Error building module config: {e}"
