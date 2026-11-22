"""Config validation MCP tools.

Tools: validate_config, cross_validate_config
"""
from __future__ import annotations

import math
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

    @mcp.tool()
    def cross_validate_config() -> str:
        """Cross-validate dashboard numbers for consistency.

        This tool performs deeper checks than validate_config():
        - KPI vs Chart consistency: if a KPI sums a column and a chart breaks it down,
          the chart total should match the KPI value.
        - Null detection: alerts if KPIs return NULL or zero unexpectedly.
        - Column reference check: verifies that chart x/y/column/valores fields
          actually exist in the query results.
        - Data quality: detects if all chart bars have the same value (possible aggregation error).

        Use this AFTER validate_config() passes to ensure the dashboard numbers
        are not only valid SQL but also internally consistent.

        Returns:
            A detailed cross-validation report with warnings and errors.
        """
        config = _load_config(CONFIG_PATH)
        if not config:
            return "No config file found. Run generate_config or update_config first."

        lines = ["=== Cross-Validation Report ===", ""]
        warnings = 0
        errors = 0

        for mod in config.get("modulos", []):
            mod_name = mod.get("nombre", "Unknown")
            lines.append(f"Module: {mod_name}")
            lines.append("")

            # Collect KPI values for cross-reference
            kpi_values = {}
            for kpi in mod.get("kpis", []):
                label = kpi.get("label", "?")
                sql = kpi.get("sql", "")
                try:
                    df = _run_query(sql)
                    if df.empty:
                        lines.append(f"  ⚠ KPI '{label}': returns empty result")
                        warnings += 1
                    else:
                        val = df.iloc[0, 0]
                        kpi_values[label] = val
                        if val is None or (isinstance(val, float) and math.isnan(val)):
                            lines.append(f"  ⚠ KPI '{label}': returns NULL")
                            warnings += 1
                        elif val == 0:
                            lines.append(f"  ⚠ KPI '{label}': returns 0 (may be suspicious)")
                            warnings += 1
                        else:
                            lines.append(f"  ✓ KPI '{label}': {val}")
                except Exception as e:
                    lines.append(f"  ✗ KPI '{label}': {e}")
                    errors += 1

            lines.append("")

            # Check chart column references
            for ch in mod.get("graficos", []):
                titulo = ch.get("titulo", "?")
                sql = ch.get("sql", "")
                x_col = ch.get("x", "")
                y_col = ch.get("y", ch.get("columna", ch.get("valores", "")))

                try:
                    df = _run_query(sql)
                    if df.empty:
                        lines.append(f"  ⚠ Chart '{titulo}': returns empty result")
                        warnings += 1
                        continue

                    # Check column references
                    missing = []
                    if x_col and x_col not in df.columns:
                        missing.append(x_col)
                    if y_col and y_col not in df.columns:
                        missing.append(y_col)

                    if missing:
                        lines.append(
                            f"  ✗ Chart '{titulo}': missing columns {missing} "
                            f"(available: {list(df.columns)})"
                        )
                        errors += 1
                    else:
                        lines.append(f"  ✓ Chart '{titulo}': columns valid ({len(df)} rows)")

                    # Check for nulls in data
                    if x_col and df[x_col].isna().any():
                        lines.append(f"  ⚠ Chart '{titulo}': null values in '{x_col}'")
                        warnings += 1

                    # Check if all bars have same value (possible aggregation error)
                    if y_col and df[y_col].notna().any():
                        unique_vals = df[y_col].dropna().nunique()
                        if unique_vals == 1 and len(df) > 1:
                            lines.append(
                                f"  ⚠ Chart '{titulo}': all bars have the same value "
                                f"(possible aggregation error)"
                            )
                            warnings += 1

                except Exception as e:
                    lines.append(f"  ✗ Chart '{titulo}': {e}")
                    errors += 1

            lines.append("")

            # KPI vs Chart consistency check
            # If a KPI sums a column and a chart breaks it down, totals should match
            for kpi in mod.get("kpis", []):
                kpi_label = kpi.get("label", "?")
                kpi_sql = kpi.get("sql", "").upper()
                kpi_val = kpi_values.get(kpi_label)
                if kpi_val is None:
                    continue

                # Only check numeric KPIs that use SUM
                if "SUM(" not in kpi_sql:
                    continue

                for ch in mod.get("graficos", []):
                    ch_sql = ch.get("sql", "").upper()
                    # If the chart uses similar aggregation on the same column
                    if "SUM(" not in ch_sql:
                        continue

                    try:
                        ch_df = _run_query(ch.get("sql", ""))
                        if ch_df.empty:
                            continue

                        y_col = ch.get("y", ch.get("columna", ch.get("valores", "")))
                        if y_col and y_col in ch_df.columns:
                            chart_total = ch_df[y_col].sum()
                            if isinstance(chart_total, (int, float)) and isinstance(kpi_val, (int, float)):
                                # Allow 1% tolerance for rounding
                                if kpi_val != 0:
                                    diff_pct = abs(chart_total - kpi_val) / abs(kpi_val) * 100
                                    if diff_pct > 1.0:
                                        lines.append(
                                            f"  ✗ Consistency: KPI '{kpi_label}' = {kpi_val}, "
                                            f"but chart '{ch.get('titulo', '?')}' sums to {chart_total} "
                                            f"({diff_pct:.1f}% difference)"
                                        )
                                        errors += 1
                    except Exception:
                        pass  # Skip if chart query fails (already reported above)

            lines.append("")

        lines.append("=== Summary ===")
        lines.append(f"  Errors: {errors}")
        lines.append(f"  Warnings: {warnings}")

        if errors == 0 and warnings == 0:
            lines.append("\n✅ All numbers are consistent!")
        elif errors == 0:
            lines.append(f"\n⚠️  No errors, but {warnings} warning(s) — review above.")
        else:
            lines.append(f"\n❌ {errors} error(s) found — the dashboard may show inconsistent numbers.")

        return "\n".join(lines)
