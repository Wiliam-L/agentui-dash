"""Dashboard audit MCP tool.

This tool provides a comprehensive audit of the generated dashboard to verify
that everything presented is truthful, consistent, and complete. It acts as a
"second pair of eyes" that questions the LLM's decisions.

Tool: audit_dashboard
"""
from __future__ import annotations

import math
import time

from fastmcp import FastMCP

from agentui_mcp.utils import CONFIG_PATH

from app_base.core.data import (
    available_tables as _available_tables,
    run_query as _run_query,
)
from app_base.core.tools import (
    load_config as _load_config,
    _validate_config,
    _validate_sql_in_config,
)


def register_audit_tools(mcp: FastMCP) -> None:
    """Register audit tools on the MCP server."""

    @mcp.tool()
    def audit_dashboard() -> str:
        """Comprehensive audit of the generated dashboard for truthfulness and quality.

        This tool goes beyond basic validation to question the LLM's decisions:
        - Are the correct tables used in the config?
        - Do KPIs make sense (no NULLs, no zeros when they shouldn't be)?
        - Do charts show what they claim (correct columns, reasonable data)?
        - Is the dashboard complete (no empty modules, broken filters)?
        - Is the SQL safe (no cartesian products, proper aggregations)?
        - Are KPIs consistent with chart totals (cross-validation)?

        Use this AFTER generate_config() and validate_config() as the final
        quality gate before delivering the dashboard to the user.

        Returns:
            A detailed audit report with PASS/WARN/FAIL status for each check.
        """
        config = _load_config(CONFIG_PATH)
        if not config:
            return (
                "No config file found. Run generate_config() or update_config() first."
            )

        lines: list[str] = []
        issues: list[tuple[str, str]] = []  # (level, message)

        def add(level: str, msg: str) -> None:
            issues.append((level, msg))

        # ── 1. STRUCTURE ──────────────────────────────────────────────
        struct_errors = _validate_config(config)
        sql_errors = _validate_sql_in_config(config)

        if struct_errors:
            for e in struct_errors:
                add("FAIL", f"Structure: {e}")
        if sql_errors:
            for e in sql_errors:
                add("FAIL", f"SQL syntax: {e}")

        # ── 2. TABLE REFERENCES ──────────────────────────────────────
        available = _available_tables()
        if not available:
            add("FAIL", "No tables available in the database.")
        else:
            # Check if config references tables that exist
            all_sql = _collect_all_sql(config)
            for sql in all_sql:
                referenced = _extract_referenced_tables(sql)
                for tbl in referenced:
                    if tbl not in available:
                        add("FAIL", f"Config references table '{tbl}' which does not exist. Available: {', '.join(available)}")

            # Check if loaded tables are ignored
            modules = config.get("modulos", [])
            if modules:
                used_tables = set()
                for mod in modules:
                    for kpi in mod.get("kpis", []):
                        used_tables.update(_extract_referenced_tables(kpi.get("sql", "")))
                    for ch in mod.get("graficos", []):
                        used_tables.update(_extract_referenced_tables(ch.get("sql", "")))
                    for tbl_item in mod.get("tablas", []):
                        used_tables.update(_extract_referenced_tables(tbl_item.get("sql", "")))

                unused = set(available) - used_tables
                if unused:
                    add("WARN", f"Loaded tables not used in config: {', '.join(sorted(unused))}. The LLM may have ignored related data.")

        # ── 3. KPI QUALITY ───────────────────────────────────────────
        for mod in modules:
            mod_name = mod.get("nombre", "Unknown")
            for kpi in mod.get("kpis", []):
                label = kpi.get("label", "?")
                sql = kpi.get("sql", "")
                try:
                    df = _run_query(sql)
                    if df.empty:
                        add("WARN", f"KPI '{label}' in '{mod_name}' returns empty result.")
                        continue
                    val = df.iloc[0, 0]
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        add("WARN", f"KPI '{label}' in '{mod_name}' returns NULL.")
                    elif isinstance(val, (int, float)) and val == 0:
                        add("WARN", f"KPI '{label}' in '{mod_name}' returns 0 — verify this is expected.")
                except Exception as e:
                    add("FAIL", f"KPI '{label}' in '{mod_name}' failed: {e}")

        # ── 4. CHART QUALITY ─────────────────────────────────────────
        for mod in modules:
            mod_name = mod.get("nombre", "Unknown")
            for ch in mod.get("graficos", []):
                titulo = ch.get("titulo", "?")
                sql = ch.get("sql", "")
                chart_type = ch.get("tipo", "")
                x_col = ch.get("x", "")
                y_col = ch.get("y", "")
                try:
                    df = _run_query(sql)
                    if df.empty:
                        add("WARN", f"Chart '{titulo}' in '{mod_name}' returns empty result.")
                        continue

                    # Check column references
                    if x_col and x_col not in df.columns:
                        add("FAIL", f"Chart '{titulo}' references column '{x_col}' which is not in query results. Available: {list(df.columns)}")
                    if y_col and y_col not in df.columns:
                        add("FAIL", f"Chart '{titulo}' references column '{y_col}' which is not in query results. Available: {list(df.columns)}")

                    # Check for NULLs in data
                    for col in [x_col, y_col]:
                        if col and col in df.columns:
                            null_count = df[col].isna().sum()
                            if null_count > 0:
                                add("WARN", f"Chart '{titulo}' has {null_count} NULL values in column '{col}'.")

                    # Pie chart with too many categories
                    if chart_type == "pie" and len(df) > 10:
                        add("WARN", f"Chart '{titulo}' is a pie chart with {len(df)} categories — consider using a bar chart for readability.")

                    # Single bar in bar chart
                    if chart_type in ("bar", "bar_h", "bar_grouped", "bar_stacked") and len(df) == 1:
                        add("WARN", f"Chart '{titulo}' only shows 1 bar — verify the GROUP BY is correct.")

                    # All same values
                    if y_col and y_col in df.columns and len(df) > 1:
                        unique_vals = df[y_col].nunique()
                        if unique_vals == 1:
                            add("WARN", f"Chart '{titulo}' has all identical values in '{y_col}' — possible aggregation error.")

                except Exception as e:
                    add("FAIL", f"Chart '{titulo}' in '{mod_name}' failed: {e}")

        # ── 5. CROSS-VALIDATION: KPI vs Chart consistency ────────────
        for mod in modules:
            mod_name = mod.get("nombre", "Unknown")
            kpis = mod.get("kpis", [])
            charts = mod.get("graficos", [])

            # Try to match KPIs with charts that might represent the same metric
            for kpi in kpis:
                kpi_sql = kpi.get("sql", "")
                kpi_label = kpi.get("label", "")
                try:
                    kpi_df = _run_query(kpi_sql)
                    if kpi_df.empty:
                        continue
                    kpi_val = kpi_df.iloc[0, 0]
                    if kpi_val is None or (isinstance(kpi_val, float) and math.isnan(kpi_val)):
                        continue

                    # Check if any chart's total matches the KPI
                    for ch in charts:
                        ch_sql = ch.get("sql", "")
                        ch_titulo = ch.get("titulo", "")
                        y_col = ch.get("y", "")
                        if not y_col or not ch_sql:
                            continue
                        try:
                            ch_df = _run_query(ch_sql)
                            if ch_df.empty or y_col not in ch_df.columns:
                                continue
                            chart_total = ch_df[y_col].sum()
                            if chart_total is None or (isinstance(chart_total, float) and math.isnan(chart_total)):
                                continue
                            # Compare with tolerance for floating point
                            if isinstance(kpi_val, (int, float)) and isinstance(chart_total, (int, float)):
                                if kpi_val != 0:
                                    ratio = abs(chart_total - kpi_val) / abs(kpi_val)
                                    if ratio > 0.01:  # 1% tolerance
                                        add(
                                            "WARN",
                                            f"KPI '{kpi_label}' ({kpi_val}) and chart '{ch_titulo}' total ({chart_total}) "
                                            f"differ by {ratio*100:.1f}% — verify they measure the same metric.",
                                        )
                        except Exception:
                            pass  # Chart may use different aggregation
                except Exception:
                    pass

        # ── 6. FILTER QUALITY ────────────────────────────────────────
        filters = config.get("filtros_globales", [])
        for f in filters:
            f_name = f.get("nombre", "?")
            f_col = f.get("columna", "")
            f_table = f.get("tabla", "")
            if f_table and f_table not in available:
                add("FAIL", f"Filter '{f_name}' references table '{f_table}' which does not exist.")
            if f_col and f_table and f_table in available:
                try:
                    col_df = _run_query(f'SELECT * FROM "{f_table}" LIMIT 1')
                    if f_col not in col_df.columns:
                        add("FAIL", f"Filter '{f_name}' references column '{f_col}' which does not exist in table '{f_table}'.")
                except Exception:
                    pass

        # ── 7. MODULE COMPLETENESS ───────────────────────────────────
        for mod in modules:
            mod_name = mod.get("nombre", "Unknown")
            if not mod.get("kpis") and not mod.get("graficos") and not mod.get("tablas"):
                add("WARN", f"Module '{mod_name}' is empty — no KPIs, charts, or tables.")

        # ── 7.5. ICON VALIDATION — No emojis allowed ─────────────────
        _check_emoji_icons(config, add)

        # ── 8. SQL SAFETY ────────────────────────────────────────────
        all_sql = _collect_all_sql(config)
        for sql in all_sql:
            # Check for potential cartesian products (multiple tables without JOIN condition)
            if "JOIN" in sql.upper():
                join_count = sql.upper().count("JOIN")
                on_count = sql.upper().count("ON")
                if join_count > on_count:
                    add("WARN", f"SQL may have cartesian product: {join_count} JOINs but only {on_count} ON clauses.")

        # ── BUILD REPORT ─────────────────────────────────────────────
        fail_count = sum(1 for lvl, _ in issues if lvl == "FAIL")
        warn_count = sum(1 for lvl, _ in issues if lvl == "WARN")
        pass_count = len(issues) - fail_count - warn_count

        lines.append("=== Dashboard Audit Report ===")
        lines.append("")
        lines.append(f"Total checks: {len(issues)}")
        lines.append(f"  ✅ Pass: {pass_count}")
        lines.append(f"  ⚠️  Warnings: {warn_count}")
        lines.append(f"  ❌ Failures: {fail_count}")
        lines.append("")

        if fail_count > 0:
            lines.append("❌ FAILURES (must fix before delivering):")
            for lvl, msg in issues:
                if lvl == "FAIL":
                    lines.append(f"   - {msg}")
            lines.append("")

        if warn_count > 0:
            lines.append("⚠️  WARNINGS (review and consider fixing):")
            for lvl, msg in issues:
                if lvl == "WARN":
                    lines.append(f"   - {msg}")
            lines.append("")

        if fail_count == 0 and warn_count == 0:
            lines.append("✅ Dashboard passed all audit checks — ready to deliver.")
        elif fail_count == 0:
            lines.append("⚠️  Dashboard has warnings but no critical failures.")
            lines.append("   Review the warnings above and fix if necessary before delivering.")
        else:
            lines.append("❌ Dashboard has critical failures that must be fixed.")
            lines.append("   Use update_config() to correct the issues, then re-run audit_dashboard().")

        return "\n".join(lines)


def _collect_all_sql(config: dict) -> list[str]:
    """Collect all SQL queries from the config."""
    sqls: list[str] = []
    for mod in config.get("modulos", []):
        for kpi in mod.get("kpis", []):
            sql = kpi.get("sql", "")
            if sql:
                sqls.append(sql)
        for ch in mod.get("graficos", []):
            sql = ch.get("sql", "")
            if sql:
                sqls.append(sql)
        for tbl in mod.get("tablas", []):
            sql = tbl.get("sql", "")
            if sql:
                sqls.append(sql)
    return sqls


def _extract_referenced_tables(sql: str) -> list[str]:
    """Extract table names referenced in a SQL query."""
    tables: list[str] = []
    if not sql:
        return tables

    # Simple extraction: look for FROM and JOIN clauses
    import re
    # Match FROM "table" or FROM table
    for match in re.finditer(r'(?:FROM|JOIN)\s+("?)(\w+)\1', sql, re.IGNORECASE):
        tables.append(match.group(2))
    return tables


def _check_emoji_icons(config: dict, add: callable) -> None:
    """Check that icon fields contain Material Icon names, not emojis."""
    import unicodedata

    icon_fields = ("icono", "material_icon", "brand_icon")

    def _has_emoji(text: str) -> bool:
        if not text or not isinstance(text, str):
            return False
        for ch in text:
            cat = unicodedata.category(ch)
            # Emojis are typically in "So" (Symbol, other) category
            # or have specific emoji properties
            if cat == "So" or ord(ch) > 0x1F000:
                return True
        return False

    # Check top-level brand_icon
    brand_icon = config.get("brand_icon", "")
    if _has_emoji(brand_icon):
        add("FAIL", f"brand_icon contains emoji ({brand_icon!r}). Use a Material Icon name like 'dashboard'.")

    # Check modules
    for mod in config.get("modulos", []):
        mod_name = mod.get("nombre", "Unknown")
        for field in icon_fields:
            val = mod.get(field, "")
            if _has_emoji(val):
                add("FAIL", f"Module '{mod_name}' has emoji in '{field}' ({val!r}). Use a Material Icon name.")

        # Check KPIs
        for kpi in mod.get("kpis", []):
            kpi_label = kpi.get("label", "?")
            for field in icon_fields:
                val = kpi.get(field, "")
                if _has_emoji(val):
                    add("FAIL", f"KPI '{kpi_label}' in '{mod_name}' has emoji in '{field}' ({val!r}). Use a Material Icon name.")

        # Check charts
        for ch in mod.get("graficos", []):
            ch_title = ch.get("titulo", "?")
            for field in icon_fields:
                val = ch.get(field, "")
                if _has_emoji(val):
                    add("FAIL", f"Chart '{ch_title}' in '{mod_name}' has emoji in '{field}' ({val!r}). Use a Material Icon name.")

        # Check tables
        for tbl in mod.get("tablas", []):
            tbl_title = tbl.get("titulo", "?")
            for field in icon_fields:
                val = tbl.get(field, "")
                if _has_emoji(val):
                    add("FAIL", f"Table '{tbl_title}' in '{mod_name}' has emoji in '{field}' ({val!r}). Use a Material Icon name.")
