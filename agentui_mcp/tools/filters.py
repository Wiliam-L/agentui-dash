"""Filter MCP tools.

Tools: get_filter_options, get_date_range
"""
from __future__ import annotations

import json

from fastmcp import FastMCP

from app_base.core.data import has_data
from app_base.core.tools import (
    get_filter_options as _get_filter_options,
    get_date_range as _get_date_range,
)


def register_filter_tools(mcp: FastMCP) -> None:
    """Register filter tools on the MCP server."""

    @mcp.tool()
    def get_filter_options(filter_json: str) -> str:
        """Get distinct values for a filter column.

        Args:
            filter_json: JSON string with filter config, e.g.:
                {"nombre": "branch", "columna": "branch", "tabla": "sales", "tipo": "select"}

        Returns:
            List of distinct values.
        """
        if not has_data():
            return "No data loaded."

        try:
            filtro_config = json.loads(filter_json)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        try:
            options = _get_filter_options(filtro_config)
            nombre = filtro_config.get("nombre", "filter")
            return (
                f"Options for '{nombre}' ({len(options)} values):\n"
                + "\n".join(f"  - {o}" for o in options)
            )
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
        if not has_data():
            return "No data loaded."

        try:
            filtro_config = json.loads(filter_json)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        try:
            min_date, max_date = _get_date_range(filtro_config)
            return f"Date range: {min_date} to {max_date}"
        except Exception as e:
            return f"Error: {e}"
