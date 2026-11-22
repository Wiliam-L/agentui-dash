# Installation Guide

## Prerequisites

**uv** — a fast Python package installer. `uv` automatically downloads and installs Python 3.11+ if you don't have it.

### Install uv

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Option A: Pre-built Package (Recommended)

Download the `.whl` file from `build_mcp/` and install it globally:

```powershell
uv tool install agentui_dash-0.1.0-py3-none-any.whl
```

After installation, two commands are available globally:

| Command | Description |
|---|---|
| `ui` | Start the Streamlit dashboard |
| `agentui-mcp` | Start the MCP server for AI agents |

---

## Option B: From Source Code

Clone the repository and install from the root directory:

```powershell
git clone https://github.com/Wiliam-L/agentui-dash.git
cd agentui-dash
uv sync
```

Run with:
```powershell
uv run ui          # Start dashboard
uv run agentui-mcp # Start MCP server
```

---

## Option C: Docker

For a fully isolated environment without installing Python or `uv`:

```powershell
docker compose up --build
```

The dashboard will be available at `http://localhost:8501`.

---

## Connecting an AI Agent

### Opencode

If you installed with `uv tool install`:

```powershell
opencode mcp add agentui-dash --global -- agentui-mcp
opencode mcp list
```

### Claude Desktop

Edit `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "uv",
      "args": ["run", "agentui-mcp"],
      "cwd": "C:\\path\\to\\agentui-dash"
    }
  }
}
```

### Cursor

`Ctrl+Shift+P` → *Cursor: Manage MCP Servers* → Add `agentui-mcp`.

### Windsurf

*Settings* → *MCP Servers* → Add `agentui-mcp`.

### Docker (MCP Server)

**Option 1: docker compose (recommended)**
```powershell
docker compose run --rm mcp
```

**Option 2: docker run**
```powershell
docker run -i --rm agentui-dash python -m agentui_mcp.server
```

---

## Troubleshooting

### WinError 64 on Windows + Python 3.14

Streamlit's default IPv6 bind may fail intermittently. To fix, bind to IPv4:

```powershell
$env:AGENTUI_HOST = "0.0.0.0"
$env:AGENTUI_PORT = "8501"
uv run ui
```

### MCP Server Not Found

If `agentui-mcp` is not in your PATH after `uv tool install`, use:

```powershell
opencode mcp add agentui-dash --global -- python -m agentui_mcp
```
