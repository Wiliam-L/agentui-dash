# AgentUI Dash — Pre-built Package

This directory contains a **pre-built wheel** ready to install, plus build scripts to regenerate it.

## Quick install (no build needed)

If you have Python ≥3.10 and `uv` installed:

```bash
uv pip install --system agentui_dash-0.1.0-py3-none-any.whl
```

After installation, two commands are available:

| Command | Description |
|---|---|
| `ui` | Start the Streamlit dashboard UI |
| `agentui-mcp` | Start the MCP server for AI agents |

## Rebuild from source

If you need to rebuild the wheel from the latest source code:

```bash
# Windows (PowerShell)
.\build.ps1

# Linux / macOS
bash build.sh
```

Or manually from the project root:

```bash
uv build
```

## Docker alternative

For a fully isolated environment without installing Python or `uv`:

```bash
docker compose up --build
```

This starts both the UI (port 8501) and the MCP server in separate containers.
