"""Query execution MCP tools.

Tools: run_query, run_query_with_filters, get_kpi
"""
from __future__ import annotations

import json

from fastmcp import FastMCP

from app_base.core.data import (
    has_data,
    run_query as _run_query,
    last_error,
    error_count,
)
from app_base.core.tools import (
    execute_query as _execute_query,
    execute_kpi as _execute_kpi,
)


def register_query_tools(mcp: FastMCP) -> None:
    """Register query tools on the MCP server."""

    @mcp.tool()
    def run_query(sql: str) -> str:
        """Execute a SQL query against the DuckDB database.

        Args:
            sql: SQL query string (e.g. "SELECT branch, SUM(total_usd) FROM sales GROUP BY branch").

        Returns:
            Query results as a formatted table (CSV-like) or error message.
        """
        if not has_data():
            return "No data loaded. Upload CSV files first."

        try:
            df = _run_query(sql)
        except Exception as e:
            return f"Query error: {e}"

        if df.empty:
            return f"Query error: {last_error()}" if last_error() else "Query returned no results."

        csv_output = df.to_csv(index=False)
        n_rows = len(df)
        n_cols = len(df.columns)

        return f"Query returned {n_rows} rows × {n_cols} columns:\n\n{csv_output}"

    @mcp.tool()
    def run_query_with_filters(sql: str, filters_json: str) -> str:
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
        if not has_data():
            return "No data loaded. Upload CSV files first."

        try:
            filters_data = json.loads(filters_json)
            filtros_config = filters_data.get("filtros_config", [])
            filtros_valores = filters_data.get("filtros_valores", {})
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        query_config = {"sql": sql}
        try:
            df = _execute_query(query_config, filtros_config, filtros_valores)
        except Exception as e:
            return f"Query error: {e}"

        if df.empty:
            return f"Query error: {last_error()}" if last_error() else "Query returned no results."

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
        if not has_data():
            return "No data loaded."

        try:
            kpi_config = json.loads(kpi_json)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        try:
            errores_antes = error_count()
            valor = _execute_kpi(kpi_config)
            if error_count() != errores_antes:
                return f"KPI error: {last_error()}"
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
