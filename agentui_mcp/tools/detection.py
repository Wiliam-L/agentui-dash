"""Column detection MCP tools.

Tools: detect_columns, get_available_roles
"""
from __future__ import annotations

from fastmcp import FastMCP

from app_base.core.data import (
    table_exists,
    available_tables,
    run_query as _run_query,
)
from app_base.core.inference import (
    _ROLES,
    _detect_physical_columns,
)


def register_detection_tools(mcp: FastMCP) -> None:
    """Register column detection tools on the MCP server."""

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
        if not table_exists(table_name):
            available = available_tables()
            if not available:
                return "No tables loaded."
            return f"Table '{table_name}' not found. Available: {', '.join(available)}"

        try:
            df = _run_query(f"SELECT * FROM {table_name} LIMIT 100")
        except Exception as e:
            return f"Error reading table: {e}"

        best_type = None
        best_mapping = {}
        for tipo in _ROLES:
            mapping = _detect_physical_columns(df, tipo)
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
                lines.append(
                    f"    {rol}: {', '.join(synonyms[:5])}{'...' if len(synonyms) > 5 else ''}"
                )

        return "\n".join(lines)
