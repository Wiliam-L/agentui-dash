"""Allow running the MCP server with: python -m agentui_mcp"""
from .server import mcp

if __name__ == "__main__":
    print("Starting MCP server (stdio transport)...", flush=True)
    mcp.run(transport="stdio")
