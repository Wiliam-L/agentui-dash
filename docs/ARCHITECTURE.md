# Architecture

## Overview

AgentUI Dash follows the **Dumb Skeleton** pattern: the UI and data layer are blind to column names. All intelligence lives in `core/inference.py`, and all state is described in a single file — `ui_config.json` — written by the MCP server.

```
User  →  AI Agent  →  MCP Server  →  ui_config.json  →  Streamlit UI  →  DuckDB
```

## Workflow

1. **User** provides a data file (CSV or Excel) to the AI agent.
2. **Agent** calls `create_dashboard()`, which chains: ingest → column detection → KPIs → charts → filters → config save.
3. **MCP Server** detects column roles, generates SQL, and atomically writes `ui_config.json`.
4. **ui_config.json** is the contract: modules, global filters, KPIs with SQL, chart specs, and column mapping.
5. **Streamlit UI** watches the JSON modification timestamp and auto-refreshes when it changes (no server restart).
6. **DuckDB** executes queries with ephemeral read-only connections.

## Components

| Component | Role | Technology |
|---|---|---|
| `app_base/streamlit_ui/` | Reactive UI that renders `ui_config.json` | Streamlit, Plotly, CSS |
| `app_base/core/data.py` | Raw data layer: ingest and SQL execution | DuckDB, pandas |
| `app_base/core/tools.py` | JSON ↔ DuckDB bridge: validates, saves, executes | Python |
| `app_base/core/inference.py` | Intelligence: maps physical columns to logical roles | Python |
| `app_base/core/chart_builder.py` | Chart construction and Plotly styling | Plotly |
| `app_base/ui_config.json` | Complete dashboard contract | JSON |
| `agentui_mcp/server.py` | MCP server exposed to the AI agent | FastMCP |
| `agentui_mcp/tools/` | Categorized MCP tool implementations | Python |

## Separation of Responsibilities

- **The MCP writes** `ui_config.json`.
- **The UI reads** `ui_config.json` and knows nothing about business logic.
- **`core/tools.py`** translates config to queries and validates JSON.
- **`core/data.py`** only executes SQL; never guesses columns or types.
- **`core/inference.py`** concentrates synonyms and detection heuristics.

The advantage is direct: the same system serves sales, inventory, logistics, or any other domain by changing only the input data.

## Repository Structure

```
.
├── pyproject.toml              # Project root (uv sync / uv run ui)
├── .streamlit/config.toml      # Light theme
├── Dockerfile                  # Docker image
├── docker-compose.yml          # UI and MCP services
├── app_base/
│   ├── .streamlit/config.toml  # Light theme (app)
│   ├── core/                   # data.py · tools.py · inference.py · chart_builder.py
│   ├── streamlit_ui/           # main.py · views/ · styles/
│   └── ui_config.json          # Dashboard contract
├── agentui_mcp/
│   ├── server.py               # MCP server (entry point)
│   ├── instructions.py         # Agent instructions
│   ├── utils.py                # Shared helpers
│   └── tools/                  # Tools by category
├── docs/
│   ├── TOOLS.md                # MCP tools reference
│   ├── INSTALL.md              # Installation guide
│   └── ARCHITECTURE.md         # This file
├── build_mcp/                  # Pre-built wheel and build scripts
└── tests/
    ├── test_inference.py       # Inference and SQL security tests
    ├── test_mcp_tools.py       # MCP tool tests
    └── fixtures/               # Test data
```

## Security

- **Read-only queries** — the UI opens DuckDB in `read_only` mode.
- **SQL allow-list** — `safe_sql()` uses `sqlglot` to parse the AST and block write operations, file access, or network access.
- **Cross-validation** — `cross_validate_config()` verifies KPI totals match chart sums, detects nulls, and checks column references.
- **Atomic JSON write** — the MCP writes to a temp file and replaces with `os.replace`; the UI never reads a half-written JSON.
- **Last valid config** — if the JSON is momentarily unreadable, the last good config is kept in session state.
- **Ephemeral connections** — connections are opened and closed per query to avoid file locking between MCP and Streamlit on Windows.
