# AgentUI Dash

**Generate a corporate dashboard from a CSV in minutes using an AI agent.**

AgentUI Dash connects an AI agent (via MCP) with DuckDB and Streamlit to create functional dashboards: the agent loads data, detects columns, generates KPIs and charts, and delivers a ready-to-use dashboard. Numbers are validated with automatic cross-validation.

## Who is it for?

For **freelancers and agencies** that build dashboards for clients.

| Without AgentUI Dash | With AgentUI Dash |
|---|---|
| Hours of SQL and Python code | Minutes with a prompt |
| Risk of calculation errors | Automatic cross-validation |
| One dashboard per project | Reusable with any CSV |

## Quickstart

**Step 1 — Install uv** (downloads Python automatically)

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Step 2 — Install the package**

Download the `.whl` file from [build_mcp/](build_mcp/) and install it:

```powershell
uv tool install build_mcp/agentui_dash-0.1.0-py3-none-any.whl
```

**Step 3 — Connect with Opencode**

```powershell
opencode mcp add agentui-dash --global -- agentui-mcp
```

**Step 4 — Try with sample data**

A sample CSV is included in [`examples/ventas.csv`](examples/ventas.csv). Tell the agent:

> "I have `examples/ventas.csv`, create a dashboard for me."

The agent will call `create_dashboard()` and return the result URL.

## How it works

```
User  →  AI Agent  →  MCP Server  →  ui_config.json  →  Streamlit UI  →  DuckDB
```

1. The user provides a CSV or Excel file to the agent.
2. The agent ingests data into DuckDB, detects column roles, and generates KPIs and charts.
3. The MCP writes `ui_config.json` — the complete dashboard contract.
4. Streamlit reads the JSON and renders the UI. If the JSON changes, it updates in hot without restarting.

[Detailed architecture →](docs/ARCHITECTURE.md)

## Why you can trust the numbers

- **`cross_validate_config()`** — verifies that KPI totals match chart bar sums. If they don't match, it alerts the agent to fix it.
- **`safe_sql()`** — uses `sqlglot` to parse the AST of every query and blocks write operations, file access, or network access before execution.
- **`validate_config()`** — executes every SQL query in the config and verifies it returns valid results.
- **Column validation** — when updating data, it checks that the new file's columns match the expected ones.

## MCP Tools

The agent has access to **29 public tools** organized in categories: dashboard, data, configuration, queries, filters, detection, charts, and server.

[Full tool list →](docs/TOOLS.md)

**Chart types:** `bar`, `bar_h`, `bar_grouped`, `bar_stacked`, `line`, `pie`, `scatter`, `heatmap`

## Advanced Installation

For all installation options (source code, Docker, other MCP clients, troubleshooting):

[Installation guide →](docs/INSTALL.md)

## License

[MIT](LICENSE) — free for evaluation and demo.
