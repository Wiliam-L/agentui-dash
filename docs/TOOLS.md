# MCP Tools Reference

AgentUI Dash exposes **29 public MCP tools** accessible by any AI agent. All SQL is validated via `safe_sql()` (sqlglot), the JSON structure via `validate_config()`, and calculation consistency via `cross_validate_config()`.

## Dashboard

| Tool | Description |
|---|---|
| `create_dashboard` | One-step dashboard creation: ingest → detect → generate config → start UI |

## Data

| Tool | Description |
|---|---|
| `upload_csv` | Upload a single CSV/Excel file; creates a unique table per file |
| `upload_multiple_csvs` | Upload multiple files; each gets its own table |
| `update_data` | Update an existing table with column validation |
| `analyze_relationships` | Detect relationships between loaded tables (same schema, common columns, unrelated) |
| `preview_table` | Preview first 10 rows of a table |
| `list_tables` | List all available tables |
| `get_table_columns` | Get column names and types of a table |
| `explore_data` | Explore data statistics (counts, nulls, types) |
| `clear_data` | Clear all data and config |

## Configuration

| Tool | Description |
|---|---|
| `generate_config` | Auto-generate `ui_config.json` from loaded tables |
| `get_config` | Read the current `ui_config.json` |
| `load_config` | Load config from file |
| `update_config` | Update specific fields in `ui_config.json` |
| `validate_config` | Validate config structure and execute SQL queries |
| `cross_validate_config` | Cross-validate KPI totals match chart sums, detect nulls, check column references |

## Queries

| Tool | Description |
|---|---|
| `run_query` | Execute a read-only SQL query |
| `run_query_with_filters` | Execute SQL with global filters injected |
| `get_kpi` | Execute a single KPI query |

## Filters

| Tool | Description |
|---|---|
| `get_filter_options` | Get distinct values for a filter column |
| `get_date_range` | Get min/max dates for a date column |

## Detection

| Tool | Description |
|---|---|
| `detect_columns` | Detect column roles (branch, date, category, amount, etc.) |
| `get_available_roles` | List all available column roles |

## Chart Builder

| Tool | Description |
|---|---|
| `list_chart_types` | List available chart types (bar, pie, line, scatter, heatmap, etc.) |
| `recommend_chart` | Recommend chart type based on SQL query |
| `build_chart_config` | Build chart configuration JSON |
| `build_kpi_config` | Build KPI configuration JSON |
| `build_filter_config` | Build filter configuration JSON |
| `build_module_config` | Build complete module configuration JSON |

## Server

| Tool | Description |
|---|---|
| `start_streamlit` | Start the Streamlit dashboard server |
| `stop_streamlit` | Stop the Streamlit server |
| `check_streamlit_status` | Check if Streamlit is running |

## Supported Chart Types

`bar`, `bar_h`, `bar_grouped`, `bar_stacked`, `line`, `pie`, `scatter`, `heatmap`

## KPI Formats

`money`, `int`, `percent`, `str`
