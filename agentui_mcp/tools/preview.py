"""Data preview and exploration MCP tools.

Tools: preview_table, explore_data
"""
from __future__ import annotations

from fastmcp import FastMCP

from app_base.core.data import (
    table_exists,
    available_tables,
    run_query as _run_query,
)
from app_base.core.inference import _classify_columns


def register_preview_tools(mcp: FastMCP) -> None:
    """Register preview and exploration tools on the MCP server."""

    @mcp.tool()
    def preview_table(table_name: str, limit: int = 10) -> str:
        """Preview the first N rows of a table.

        Args:
            table_name: Table name in DuckDB.
            limit: Number of rows to preview (default: 10).

        Returns:
            Table data as CSV.
        """
        if not table_exists(table_name):
            available = available_tables()
            if not available:
                return "No tables loaded."
            return f"Table '{table_name}' not found. Available: {', '.join(available)}"

        try:
            df = _run_query(f"SELECT * FROM {table_name} LIMIT {int(limit)}")
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
        if not table_exists(table_name):
            available = available_tables()
            if not available:
                return "No tables loaded."
            return f"Table '{table_name}' not found. Available: {', '.join(available)}"

        try:
            df = _run_query(f"SELECT * FROM {table_name} LIMIT 100")
        except Exception as e:
            return f"Error reading table: {e}"

        if df.empty:
            return "Table is empty."

        try:
            count_df = _run_query(f"SELECT COUNT(*) AS n FROM {table_name}")
            total_rows = int(count_df["n"].iloc[0]) if not count_df.empty else "?"
        except Exception:
            total_rows = "?"

        classified = _classify_columns(df)
        cat_cols = classified["categorical"]
        num_cols = classified["numeric"]
        date_cols = classified["date"]
        high_card = classified["high_cardinality"]

        lines = [
            f"=== Data Exploration: '{table_name}' ===",
            "",
            f"Shape: {total_rows} rows × {len(df.columns)} columns",
            "",
            f"--- Column Classification ---",
            f"  Categorical ({len(cat_cols)}): {', '.join(cat_cols) if cat_cols else '(none)'}",
            f"  Numeric ({len(num_cols)}): {', '.join(num_cols) if num_cols else '(none)'}",
            f"  Date ({len(date_cols)}): {', '.join(date_cols) if date_cols else '(none)'}",
            f"  High cardinality ({len(high_card)}): {', '.join(high_card) if high_card else '(none)'}",
            "",
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

            if col in num_cols:
                mean_val = df[col].mean()
                min_val = df[col].min()
                max_val = df[col].max()
                lines.append(f"    Stats: min={min_val:.2f}, max={max_val:.2f}, avg={mean_val:.2f}")

            lines.append("")

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
