"""agentui-mcp — exposes app tools for AI agents via Model Context Protocol.

This server uses FastMCP with stdio transport so an AI agent (Claude, Cursor,
etc.) can call tools like `upload_csv`, `generate_config`, `run_query`, etc.

Usage:
    python server.py              # runs as stdio server
    # Or configure in your AI client:
    #   command: python
    #   args:    ["server.py"]
    #   cwd:     path/to/agentui-mcp
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure app_base/ is on sys.path so `core` is importable.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent / "app_base"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastmcp import FastMCP

from agentui_mcp.instructions import MCP_INSTRUCTIONS
from agentui_mcp.tools.streamlit import register_streamlit_tools
from agentui_mcp.tools.data import register_data_tools
from agentui_mcp.tools.config import register_config_tools
from agentui_mcp.tools.query import register_query_tools
from agentui_mcp.tools.filters import register_filter_tools
from agentui_mcp.tools.detection import register_detection_tools
from agentui_mcp.tools.validation import register_validation_tools
from agentui_mcp.tools.preview import register_preview_tools
from agentui_mcp.tools.chart_builder import register_chart_builder_tools
from agentui_mcp.tools.audit import register_audit_tools


mcp = FastMCP(
    name="AgentUI Dashboard",
    instructions=MCP_INSTRUCTIONS,
)

# Register all tool categories
register_streamlit_tools(mcp)
register_data_tools(mcp)
register_config_tools(mcp)
register_query_tools(mcp)
register_filter_tools(mcp)
register_detection_tools(mcp)
register_validation_tools(mcp)
register_preview_tools(mcp)
register_chart_builder_tools(mcp)
register_audit_tools(mcp)

def main():
    """Entry point for the agentui-mcp command."""
    # Do NOT start Streamlit here — the dashboard config (ui_config.json) and
    # database don't exist yet. Streamlit should only be launched AFTER the LLM
    # agent has generated the dashboard via create_dashboard(). The agent will
    # call start_streamlit() when ready.
    print("Starting MCP server (stdio transport)...", flush=True)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
