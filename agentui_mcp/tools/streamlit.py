"""Streamlit server management MCP tools.

Tools: start_streamlit, stop_streamlit, check_streamlit_status
"""
from __future__ import annotations

import subprocess
import sys
import time

from fastmcp import FastMCP

from agentui_mcp.utils import (
    _PROJECT_ROOT,
    _is_streamlit_running,
    get_streamlit_port,
    get_streamlit_process,
    get_streamlit_started_by_mcp,
    set_streamlit_port,
    set_streamlit_process,
    set_streamlit_started_by_mcp,
)


def register_streamlit_tools(mcp: FastMCP) -> None:
    """Register Streamlit management tools on the MCP server."""

    @mcp.tool()
    def start_streamlit(port: int = 8501) -> str:
        """Start the Streamlit dashboard server in the background.

        Launches the Streamlit app so the user can view the dashboard in their
        browser. The server auto-refreshes every 3 seconds when ui_config.json
        changes.

        Args:
            port: Port number for the server (default: 8501).

        Returns:
            The URL to open in the browser and server status.
        """
        # Check if already running
        if _is_streamlit_running():
            return (
                f"⚠️ Streamlit is already running!\n\n"
                f"URL: http://localhost:{get_streamlit_port()}\n\n"
                f"Open this URL in your browser to view the dashboard."
            )

        # Check if port is in use by another process
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
            except OSError:
                return (
                    f"⚠️ Port {port} is already in use by another process.\n\n"
                    f"Try a different port or stop the existing process first.\n"
                    f"You can check with: check_streamlit_status()"
                )

        # Find python executable (prefer venv if available)
        venv_python = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            python_exe = str(venv_python)
        else:
            python_exe = sys.executable

        streamlit_main = _PROJECT_ROOT / "streamlit_ui" / "main.py"

        # Start Streamlit in background
        try:
            log_file = _PROJECT_ROOT / "streamlit.log"
            with open(log_file, "w") as log:
                set_streamlit_process(subprocess.Popen(
                    [
                        python_exe, "-m", "streamlit", "run",
                        str(streamlit_main),
                        "--server.port", str(port),
                        "--server.headless", "true",
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=str(_PROJECT_ROOT),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                ))
            set_streamlit_started_by_mcp(True)
            set_streamlit_port(port)

            # Give it a moment to start
            time.sleep(2)

            if _is_streamlit_running():
                url = f"http://localhost:{port}"
                return (
                    f"✅ Streamlit server started successfully!\n\n"
                    f"URL: {url}\n\n"
                    f"📌 IMPORTANT: Please open this URL in your browser:\n"
                    f"  {url}\n\n"
                    f"The dashboard will auto-refresh every 3 seconds when the config changes.\n"
                    f"Tell the user to open the link above to see their dashboard."
                )
            else:
                return (
                    f"❌ Streamlit server failed to start.\n\n"
                    f"Check the log file: {log_file}\n"
                    f"Error: Process exited immediately."
                )

        except Exception as e:
            return f"❌ Error starting Streamlit: {e}"

    @mcp.tool()
    def stop_streamlit() -> str:
        """Stop the Streamlit dashboard server.

        Returns:
            Confirmation message.
        """
        if not _is_streamlit_running():
            return "Streamlit server is not running."

        try:
            proc = get_streamlit_process()
            proc.terminate()
            proc.wait(timeout=5)
            set_streamlit_process(None)
            set_streamlit_started_by_mcp(False)
            return "✅ Streamlit server stopped successfully."
        except subprocess.TimeoutExpired:
            try:
                proc = get_streamlit_process()
                proc.kill()
                set_streamlit_process(None)
                set_streamlit_started_by_mcp(False)
                return "✅ Streamlit server force-stopped."
            except Exception as e:
                return f"Error stopping Streamlit: {e}"
        except Exception as e:
            return f"Error stopping Streamlit: {e}"

    @mcp.tool()
    def check_streamlit_status() -> str:
        """Check if the Streamlit dashboard server is running.

        Returns:
            Server status and URL if running.
        """
        if _is_streamlit_running():
            proc = get_streamlit_process()
            return (
                f"✅ Streamlit server is RUNNING.\n\n"
                f"URL: http://localhost:{get_streamlit_port()}\n"
                f"PID: {proc.pid if proc else 'unknown'}\n"
                f"Started by MCP: {get_streamlit_started_by_mcp()}"
            )
        else:
            return (
                "❌ Streamlit server is NOT running.\n\n"
                "Start it with: start_streamlit()\n"
                "Or let create_dashboard() start it automatically."
            )
