"""PDF export MCP tool.

Tool: export_pdf — generates a white-label PDF report of the dashboard
and saves it to disk so the LLM can deliver it to the user.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastmcp import FastMCP

from agentui_mcp.utils import CONFIG_PATH

_logger = logging.getLogger("mcp.pdf")

# Directory where generated PDFs are stored
_EXPORT_DIR = Path(__file__).resolve().parent.parent.parent / "app_base" / "export"


def _load_config() -> dict:
    """Load the current ui_config.json."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Dashboard config not found at {CONFIG_PATH}. "
            "Generate a dashboard first with create_dashboard()."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def register_pdf_tools(mcp: FastMCP) -> None:
    """Register PDF export tools on the MCP server."""

    @mcp.tool()
    def export_pdf() -> str:
        """Export the current dashboard to a PDF report.

        Generates a complete PDF with a cover page (client brand), all KPIs,
        charts (as images), and tables from every module in the dashboard.
        The PDF is white-label — it shows only the client's brand, never
        AgentUI Dash.

        The file is saved to app_base/export/dashboard.pdf.

        Returns:
            The file path of the generated PDF and a summary of the content.
        """
        # Load config
        config = _load_config()
        brand_name = config.get("brand_name", "Dashboard")
        modulos = config.get("modulos", [])

        # Count content
        total_kpis = sum(len(m.get("kpis", [])) for m in modulos)
        total_charts = sum(len(m.get("graficos", [])) for m in modulos)
        total_tables = sum(len(m.get("tablas", [])) for m in modulos)

        # Generate PDF
        try:
            from app_base.core.pdf_export import generate_pdf_to_file
        except ImportError as exc:
            return (
                f"❌ PDF export requires weasyprint. Install it with:\n"
                f"  pip install weasyprint\n\n"
                f"Error: {exc}"
            )

        output_path = _EXPORT_DIR / "dashboard.pdf"
        _logger.info(f"Generating PDF for '{brand_name}' → {output_path}")

        try:
            generate_pdf_to_file(config, output_path)
        except ValueError as e:
            # e.g. "No data available"
            return f"❌ {e}"
        except Exception as e:
            _logger.error(f"PDF generation failed: {e}", exc_info=True)
            return f"❌ Error generating PDF: {e}"

        file_size_kb = output_path.stat().st_size / 1024

        return (
            f"✅ PDF report generated successfully!\n\n"
            f"File: {output_path}\n"
            f"Size: {file_size_kb:.1f} KB\n\n"
            f"Content:\n"
            f"  - {len(modulos)} module(s)\n"
            f"  - {total_kpis} KPI(s)\n"
            f"  - {total_charts} chart(s)\n"
            f"  - {total_tables} table(s)\n\n"
            f"The PDF is white-label and shows only the client's brand: '{brand_name}'.\n"
            f"You can share this file with the client directly."
        )
