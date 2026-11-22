"""Shared utilities for MCP tools.

This module provides common helpers used across multiple tool modules:
file wrappers, port detection, and Streamlit process management.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# --------------------------------------------------------------------------- #
# Project paths
# --------------------------------------------------------------------------- #

_PROJECT_ROOT = Path(__file__).resolve().parent.parent / "app_base"
CONFIG_PATH = _PROJECT_ROOT / "ui_config.json"

# --------------------------------------------------------------------------- #
# Streamlit process management
# --------------------------------------------------------------------------- #

_STREAMLIT_PORT = 8501
_streamlit_process: subprocess.Popen | None = None
_streamlit_started_by_mcp = False


def _find_free_port(start_port: int = 8501, max_attempts: int = 10) -> int:
    """Find an available port starting from the given port."""
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    return start_port


def _is_streamlit_running() -> bool:
    """Check if the tracked Streamlit process is still running."""
    if _streamlit_process is None:
        return False
    return _streamlit_process.poll() is None


def get_streamlit_port() -> int:
    """Return the current Streamlit port."""
    return _STREAMLIT_PORT


def set_streamlit_port(port: int) -> None:
    """Set the current Streamlit port."""
    global _STREAMLIT_PORT
    _STREAMLIT_PORT = port


def get_streamlit_process() -> subprocess.Popen | None:
    """Return the current Streamlit process."""
    return _streamlit_process


def set_streamlit_process(proc: subprocess.Popen | None) -> None:
    """Set the current Streamlit process."""
    global _streamlit_process
    _streamlit_process = proc


def get_streamlit_started_by_mcp() -> bool:
    """Return whether MCP started the Streamlit server."""
    return _streamlit_started_by_mcp


def set_streamlit_started_by_mcp(value: bool) -> None:
    """Set whether MCP started the Streamlit server."""
    global _streamlit_started_by_mcp
    _streamlit_started_by_mcp = value


# --------------------------------------------------------------------------- #
# File wrapper for DuckDB ingestion
# --------------------------------------------------------------------------- #


class FileWrapper:
    """Wraps a file path so it can be passed to ingest_table like a file upload."""

    def __init__(self, path: Path):
        self._path = path
        self._name = path.name

    def getvalue(self) -> bytes:
        return self._path.read_bytes()

    @property
    def name(self) -> str:
        return self._name
