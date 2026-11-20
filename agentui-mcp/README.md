# agentui-mcp — AgentUI Dash MCP Server

This directory contains a **Model Context Protocol (MCP)** server that exposes 21 dashboard tools for AI agents.

All documentation is embedded directly in `server.py` as MCP `instructions`. When your AI client connects to this server, the agent automatically receives the complete guide: architecture, all tools with parameters, 5 common workflows, `ui_config.json` structure, and key rules. **No extra configuration needed.**

## ⚡ Quick Setup

### Step 1: Configure MCP Server

Add this to your AI client MCP configuration:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "C:\\Users\\wlope\\Desktop\\MCP_HACKATHON - copia\\agentui-mcp",
      "enabled": true
    }
  }
}
```

### Step 2: Install Dependencies

```bash
cd "C:\Users\wlope\Desktop\MCP_HACKATHON - copia\agentui-mcp"
uv pip install -e .
```

Or from the `app_base` project (which includes `agentui-mcp` as an optional dependency):

```bash
cd "C:\Users\wlope\Desktop\MCP_HACKATHON - copia\app_base"
uv pip install -e ".[mcp]"
```

### Step 3: Done

Connect your AI agent and start asking for dashboards. The agent will receive all the instructions automatically from the MCP server.

## 25 Tools Overview

| Category | Tools |
|----------|-------|
| **Data Management** | `create_dashboard` ⭐, `upload_csv`, `upload_multiple_csvs`, `list_tables`, `get_table_columns`, `preview_table`, `clear_data` |
| **Configuration** | `generate_config`, `get_config`, `load_config`, `update_config` |
| **Queries** | `run_query`, `run_query_with_filters`, `get_kpi` |
| **Filters** | `get_filter_options`, `get_date_range` |
| **Column Detection** | `detect_columns`, `get_available_roles` |
| **Chart Builder** | `list_chart_types`, `recommend_chart`, `build_chart_config`, `build_kpi_config`, `build_filter_config`, `build_module_config` |
| **Streamlit** | `start_streamlit`, `stop_streamlit`, `check_streamlit_status` |

## Architecture

```
AI Agent → MCP Server (stdio) → core/data.py (DuckDB)
                    ↓
            core/inference.py (column detection)
                    ↓
            core/tools.py (dynamic query engine)
                    ↓
            ui_config.json → Streamlit UI (blind renderer)
```

The MCP server is the **bridge** between the AI agent and the dashboard. All tool documentation and workflows are embedded in `server.py` instructions — the agent receives them automatically on connection.
