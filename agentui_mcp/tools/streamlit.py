"""Streamlit server management MCP tools.

Tools: start_streamlit, stop_streamlit, check_streamlit_status
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastmcp import FastMCP

from agentui_mcp.utils import (
    _is_streamlit_running,
    get_streamlit_port,
    get_streamlit_process,
    get_streamlit_started_by_mcp,
    set_streamlit_port,
    set_streamlit_process,
    set_streamlit_started_by_mcp,
)


def _launch_streamlit(port: int = 8501) -> tuple[bool, str]:
    """Launch Streamlit server in the background and wait until it responds.

    Returns (success, message) tuple. This function blocks until Streamlit
    is actually responding on the port (up to 30 seconds), ensuring the
    dashboard is available before the MCP server accepts tool calls.
    """
    # Check if already running
    if _is_streamlit_running():
        return True, f"Streamlit already running on port {get_streamlit_port()}"

    # Check if port is in use by another process
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", port))
        except OSError:
            return False, f"Port {port} is already in use"

    # Locate the Streamlit script
    script_path, cwd = _find_streamlit_script()
    if not script_path.exists():
        return False, f"Streamlit script not found at {script_path}"

    host = os.environ.get("AGENTUI_HOST", "127.0.0.1")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script_path),
        f"--server.address={host}",
        f"--server.port={port}",
        "--theme.base=light",
        "--theme.primaryColor=#246bfd",
        "--theme.backgroundColor=#f8fafc",
        "--theme.secondaryBackgroundColor=#ffffff",
        "--theme.textColor=#0f172a",
        "--server.headless=true",
    ]

    try:
        log_file = Path(cwd) / "streamlit.log"
        # Keep the log file handle open by passing it directly to Popen
        # instead of using a context manager that closes it immediately.
        log_fh = open(log_file, "w")

        # DETACHED process flags: Streamlit survives when the MCP server exits.
        # On Windows: CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS makes it independent.
        # On Unix: start_new_session=True detaches from the parent process group.
        if sys.platform == "win32":
            creation_flags = (
                subprocess.CREATE_NO_WINDOW
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | 0x00000008  # DETACHED_PROCESS
            )
        else:
            creation_flags = 0

        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            creationflags=creation_flags,
            start_new_session=(sys.platform != "win32"),
        )

        # IMPORTANT: Do NOT close log_fh here. On Windows with DETACHED_PROCESS,
        # closing the parent's copy of the stdout handle causes the child process
        # to receive a broken pipe (EBADF) when it tries to write, killing it
        # silently. The detached process inherits its own copy of the handle,
        # so leaving ours open is safe — the OS will close it when this process exits.

        # We can't track the process directly since it's detached.
        # Instead, we track by port number.
        set_streamlit_process(None)
        set_streamlit_started_by_mcp(True)
        set_streamlit_port(port)

        # Wait until the server is actually responding (up to 30 seconds).
        # We only check the port — _is_streamlit_running() also uses socket connect,
        # so checking it here is redundant and causes false negatives when Streamlit
        # is still starting up (process alive but port not yet bound).
        started = False
        for _ in range(60):  # 60 * 0.5s = 30s max wait
            time.sleep(0.5)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
                    test_sock.settimeout(1)
                    test_sock.connect(("localhost", port))
                    started = True
                    break
            except (OSError, ConnectionRefusedError):
                continue

        if started:
            return True, f"Streamlit started and ready on port {port}"
        else:
            return False, f"Streamlit not responding on port {port} after 30s. Check {log_file}"

    except Exception as e:
        return False, f"Error starting Streamlit: {e}"


def _find_streamlit_script() -> tuple[Path, Path]:
    """Locate the Streamlit main.py script and its working directory.

    Returns (script_path, cwd) where script_path is the main.py file
    and cwd is the directory where Streamlit should be launched from.

    This works for both installed packages (wheel) and development mode
    (editable install or running from repo root).
    """
    # The main.py lives inside app_base/streamlit_ui/main.py relative to
    # the installed package. We resolve it via the app_base package.
    try:
        import app_base.streamlit_ui.main as main_module
        script_path = Path(main_module.__file__).resolve()
        project_root = script_path.parent.parent  # app_base/
        # If app_base is inside a repo root (has sibling app_base/), use repo root as cwd
        repo_root = project_root.parent if (project_root.parent / "app_base").is_dir() else project_root
        return script_path, repo_root
    except ImportError:
        # Fallback: look relative to this file (agentui_mcp/tools/streamlit.py)
        # In a wheel: agentui_mcp and app_base are siblings in site-packages
        this_file = Path(__file__).resolve()
        # agentui_mcp/tools/streamlit.py -> agentui_mcp/ -> site-packages/ -> app_base/
        site_packages = this_file.parent.parent.parent
        app_base_dir = site_packages / "app_base"
        script_path = app_base_dir / "streamlit_ui" / "main.py"
        return script_path, site_packages


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

        # Launch Streamlit (_launch_streamlit already waits until ready)
        success, msg = _launch_streamlit(port)
        if not success:
            return f"❌ {msg}"

        url = f"http://localhost:{port}"
        return (
            f"✅ Streamlit server started and ready!\n\n"
            f"URL: {url}\n\n"
            f"📌 IMPORTANT: Open this URL in the user's browser:\n"
            f"  {url}\n\n"
            f"The dashboard auto-refreshes every 3 seconds when the config changes.\n"
            f"Tell the user: 'Your dashboard is ready. Open it at: {url}'\n"
            f"If you have browser tools available, navigate to {url} to verify."
        )

    @mcp.tool()
    def stop_streamlit() -> str:
        """Stop the Streamlit dashboard server.

        ⚠️  WARNING: This will make the dashboard unavailable to the user.
        Only use this if the user explicitly asks to stop the dashboard.

        Returns:
            Confirmation message.
        """
        if not _is_streamlit_running():
            return "Streamlit server is not running."

        port = get_streamlit_port()
        try:
            # Find and kill the process listening on the Streamlit port
            # Since Streamlit is a detached process, we can't use the process reference.
            # Instead, we find the PID by port and kill it.
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=5
            )
            pids_to_kill = set()
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            pids_to_kill.add(int(pid))
                        except ValueError:
                            pass

            if pids_to_kill:
                for pid in pids_to_kill:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=5
                        )
                    except Exception:
                        pass
                set_streamlit_started_by_mcp(False)
                return f"✅ Streamlit server stopped successfully (port {port})."
            else:
                return f"Streamlit is not listening on port {port}."
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
