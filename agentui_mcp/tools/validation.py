"""Config validation MCP tool.

Tools: validate_config
"""
from __future__ import annotations

import time

from fastmcp import FastMCP

from agentui_mcp.utils import CONFIG_PATH

from app_base.core.data import run_query as _run_query
from app_base.core.tools import (
    load_config as _load_config,
    _validate_config,
    _validate_sql_in_config,
)


def register_validation_tools(mcp: FastMCP) -> None:
    """Register validation tools on the MCP server."""

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
        config = _load_config(CONFIG_PATH)
        if not config:
            return "No config file found. Run generate_config or update_config first."

        lines = ["=== Config Validation Report ===", ""]

        struct_errors = _validate_config(config)
        sql_errors = _validate_sql_in_config(config)

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

        lines.append("--- Query Execution Results ---")
        total = 0
        passed = 0
        failed = 0

        for mod in config.get("modulos", []):
            mod_name = mod.get("nombre", "Unknown")
            lines.append(f"\n  Module: {mod_name}")

            for kpi in mod.get("kpis", []):
                label = kpi.get("label", "?")
                sql = kpi.get("sql", "")
                total += 1
                try:
                    start = time.time()
                    df = _run_query(sql)
                    elapsed = time.time() - start
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

            for ch in mod.get("graficos", []):
                titulo = ch.get("titulo", "?")
                sql = ch.get("sql", "")
                total += 1
                try:
                    start = time.time()
                    df = _run_query(sql)
                    elapsed = time.time() - start
                    if not df.empty:
                        lines.append(f"  ✓ Chart '{titulo}': {len(df)} rows ({elapsed:.3f}s)")
                        passed += 1
                    else:
                        lines.append(f"  ⚠ Chart '{titulo}': empty result ({elapsed:.3f}s)")
                        failed += 1
                except Exception as e:
                    lines.append(f"  ✗ Chart '{titulo}': {e}")
                    failed += 1

            for tbl in mod.get("tablas", []):
                titulo = tbl.get("titulo", "?")
                sql = tbl.get("sql", "")
                total += 1
                try:
                    start = time.time()
                    df = _run_query(sql)
                    elapsed = time.time() - start
                    if not df.empty:
                        lines.append(f"  ✓ Table '{titulo}': {len(df)} rows ({elapsed:.3f}s)")
                        passed += 1
                    else:
                        lines.append(f"  ⚠ Table '{titulo}': empty result ({elapsed:.3f}s)")
                        failed += 1
                except Exception as e:
                    lines.append(f"  ✗ Table '{titulo}': {e}")
                    failed += 1

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
