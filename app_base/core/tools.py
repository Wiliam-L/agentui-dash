"""Dynamic query engine — the bridge between ui_config.json and DuckDB.

Everything is driven by JSON configuration: SQL queries, KPIs, filters, charts.
This module executes queries defined in the JSON config and returns DataFrames
that the UI renders via `render_chart()`.

No hardcoded column names, no hardcoded queries — everything comes from the config.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .data import ejecutar

_logger = logging.getLogger("tools")

# Path to the config file (same directory as this module's parent)
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "ui_config.json"

# --------------------------------------------------------------------------- #
# Filter handling
# --------------------------------------------------------------------------- #

def _build_where(filtros_config: list[dict], filtros_valores: dict) -> tuple[str, dict[str, Any]]:
    """Build a SQL WHERE clause from filter config and user-selected values.
    
    Args:
        filtros_config: List of filter definitions from JSON:
            [{"nombre": "branch", "columna": "branch", "tabla": "sales", "tipo": "select"}, ...]
        filtros_valores: Dict of user-selected values:
            {"branch": "A", "date_range": (date1, date2), ...}
    
    Returns:
        (where_clause, params) tuple for parameterized SQL.
    """
    clausulas: list[str] = []
    params: dict[str, Any] = {}
    
    for f_config in filtros_config:
        filtro_nombre = f_config["nombre"]
        columna = f_config["columna"]
        filtro_tipo = f_config.get("tipo", "select")
        
        valor = filtros_valores.get(filtro_nombre)
        if valor is None:
            continue
        
        if filtro_tipo == "select":
            # Single select — "All" means no filter
            if valor and valor != "All":
                key = f"f_{filtro_nombre}"
                clausulas.append(f'"{columna}" = ${key}')
                params[key] = valor
        
        elif filtro_tipo == "date_range":
            # Date range slider — value is a tuple (min, max)
            # OR fallback select — value is a single value or None
            if isinstance(valor, (list, tuple)) and len(valor) == 2 and valor[0] is not None and valor[1] is not None:
                key_min = f"f_{filtro_nombre}_min"
                key_max = f"f_{filtro_nombre}_max"
                clausulas.append(f'"{columna}" BETWEEN ${key_min} AND ${key_max}')
                params[key_min] = pd.Timestamp(valor[0])
                params[key_max] = pd.Timestamp(valor[1])
            elif valor is not None and valor != "All":
                # Fallback: single value from select
                key = f"f_{filtro_nombre}"
                clausulas.append(f'"{columna}" = ${key}')
                params[key] = valor
        
        elif filtro_tipo == "multiselect":
            # Multi-select
            if valor and len(valor) > 0:
                placeholders = ", ".join(f"$f_{filtro_nombre}_{i}" for i in range(len(valor)))
                for i, v in enumerate(valor):
                    params[f"f_{filtro_nombre}_{i}"] = v
                clausulas.append(f'"{columna}" IN ({placeholders})')
    
    where = " WHERE " + " AND ".join(clausulas) if clausulas else ""
    return where, params


# --------------------------------------------------------------------------- #
# Query execution
# --------------------------------------------------------------------------- #

def ejecutar_query(
    query_config: dict,
    filtros_config: list[dict] | None = None,
    filtros_valores: dict | None = None,
) -> pd.DataFrame:
    """Execute a query defined in JSON config.

    Args:
        query_config: Dict with SQL template from JSON:
            {"sql": "SELECT branch, SUM(total_usd) AS Sales FROM data GROUP BY branch"}
            Optionally supports filter placeholders: {"sql": "...", "filtros": ["branch", "date"]}
        filtros_config: Optional filter definitions for WHERE clause
        filtros_valores: Optional user-selected filter values

    Returns:
        DataFrame with query results.
    """
    sql = query_config["sql"]

    # If filters are provided, inject WHERE clause
    if filtros_config and filtros_valores:
        where, params = _build_where(filtros_config, filtros_valores)
        if where:
            # Inject WHERE before GROUP BY, ORDER BY, LIMIT, or at the end
            sql_upper = sql.upper()
            if "GROUP BY" in sql_upper:
                sql = sql[:sql_upper.index("GROUP BY")] + where + " " + sql[sql_upper.index("GROUP BY"):]
            elif "ORDER BY" in sql_upper:
                sql = sql[:sql_upper.index("ORDER BY")] + where + " " + sql[sql_upper.index("ORDER BY"):]
            elif "LIMIT" in sql_upper:
                sql = sql[:sql_upper.index("LIMIT")] + where + " " + sql[sql_upper.index("LIMIT"):]
            else:
                sql = sql + where

        return ejecutar(sql, params)

    return ejecutar(sql)


def ejecutar_kpi(
    kpi_config: dict,
    filtros_config: list[dict] | None = None,
    filtros_valores: dict | None = None,
) -> Any:
    """Execute a KPI query and return a single value.

    Args:
        kpi_config: Dict from JSON:
            {
                "icono": "payments",
                "label": "Total Sales",
                "sql": "SELECT COALESCE(SUM(total_usd), 0) AS v FROM data",
                "formato": "money",
                "sub_label": "5 branches"  (optional, can be a SQL too)
            }
        filtros_config: Optional filter definitions
        filtros_valores: Optional filter values

    Returns:
        The KPI value (float, int, or str).
    """
    df = ejecutar_query(kpi_config, filtros_config, filtros_valores)
    if df.empty:
        return 0
    
    # Get the first column's first value
    valor = df.iloc[0, 0]
    
    # Handle None/NaN
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0
    
    formato = kpi_config.get("formato", "number")
    if formato == "money":
        return float(valor)
    elif formato == "percent":
        return float(valor)
    elif formato == "int":
        return int(valor)
    else:
        return valor


# --------------------------------------------------------------------------- #
# Filter options (dynamic)
# --------------------------------------------------------------------------- #

def obtener_opciones_filtro(filtro_config: dict) -> list:
    """Get distinct values for a filter from the database.

    Args:
        filtro_config: Dict from JSON:
            {
                "nombre": "branch",
                "columna": "branch",
                "tabla": "sales",
                "tipo": "select"
            }

    Returns:
        List of distinct values for the filter.
    """
    tabla = filtro_config["tabla"]
    columna = filtro_config["columna"]

    df = ejecutar(
        f'SELECT DISTINCT "{columna}" AS v FROM {tabla} WHERE "{columna}" IS NOT NULL ORDER BY v',
    )
    if df.empty:
        return []
    return df["v"].dropna().tolist()


def obtener_rango_fechas(filtro_config: dict) -> tuple:
    """Get min/max dates for a date range filter.

    Args:
        filtro_config: Dict from JSON with "columna" and "tabla".

    Returns:
        (min_date, max_date) tuple. If the column is not a real date column,
        returns (None, None) to signal the UI to fall back to a select filter.
    """
    import datetime as _dt
    tabla = filtro_config["tabla"]
    columna = filtro_config["columna"]

    df = ejecutar(
        f'SELECT MIN("{columna}") AS mn, MAX("{columna}") AS mx FROM {tabla} WHERE "{columna}" IS NOT NULL',
    )
    if df.empty or df.iloc[0, 0] is None:
        return None, None
    
    min_val = df.iloc[0, 0]
    max_val = df.iloc[0, 1]
    
    def _as_date(v):
        if isinstance(v, _dt.datetime):
            return v.date()
        if isinstance(v, _dt.date):
            return v
        # Try pandas datetime conversion
        try:
            dt = pd.to_datetime(v)
            # Check if the result is a valid date (not epoch 1970)
            if dt.year < 1970:
                return None  # Invalid date conversion
            return dt.date()
        except Exception:
            return None
    
    min_date = _as_date(min_val)
    max_date = _as_date(max_val)
    
    # If either date is invalid or they're the same (epoch fallback), return None
    if min_date is None or max_date is None:
        return None, None
    if min_date == max_date and min_date.year == 1970:
        return None, None
    
    return min_date, max_date


# --------------------------------------------------------------------------- #
# UI Config management — validate and save ui_config.json
# --------------------------------------------------------------------------- #

def _validar_config(config: dict) -> list[str]:
    """Validate a ui_config.json structure and return a list of errors.
    
    Args:
        config: Dict to validate as ui_config.json.
    
    Returns:
        List of error strings. Empty list means valid.
    """
    errors: list[str] = []
    
    # Required top-level keys
    if "modulos" not in config or not isinstance(config["modulos"], list):
        errors.append("'modulos' must be a list of module configs.")
    
    if "filtros_globales" not in config or not isinstance(config["filtros_globales"], list):
        errors.append("'filtros_globales' must be a list of filter configs.")
    
    if "column_mapping" not in config or not isinstance(config["column_mapping"], dict):
        errors.append("'column_mapping' must be a dict mapping roles to column names.")
    
    # Validate each module
    if "modulos" in config and isinstance(config["modulos"], list):
        for i, mod in enumerate(config["modulos"]):
            if not isinstance(mod, dict):
                errors.append(f"modulos[{i}] must be a dict.")
                continue
            if "id" not in mod:
                errors.append(f"modulos[{i}] missing required key 'id'.")
            if "nombre" not in mod:
                errors.append(f"modulos[{i}] missing required key 'nombre'.")
            
            # Validate KPIs
            if "kpis" in mod:
                if not isinstance(mod["kpis"], list):
                    errors.append(f"modulos[{i}]['kpis'] must be a list.")
                else:
                    for j, kpi in enumerate(mod["kpis"]):
                        if not isinstance(kpi, dict):
                            errors.append(f"modulos[{i}]['kpis'][{j}] must be a dict.")
                            continue
                        if "sql" not in kpi:
                            errors.append(f"modulos[{i}]['kpis'][{j}] missing required key 'sql'.")
                        if "label" not in kpi:
                            errors.append(f"modulos[{i}]['kpis'][{j}] missing required key 'label'.")
            
            # Validate charts
            if "graficos" in mod:
                if not isinstance(mod["graficos"], list):
                    errors.append(f"modulos[{i}]['graficos'] must be a list.")
                else:
                    for j, ch in enumerate(mod["graficos"]):
                        if not isinstance(ch, dict):
                            errors.append(f"modulos[{i}]['graficos'][{j}] must be a dict.")
                            continue
                        if "sql" not in ch:
                            errors.append(f"modulos[{i}]['graficos'][{j}] missing required key 'sql'.")
                        if "tipo" not in ch:
                            errors.append(f"modulos[{i}]['graficos'][{j}] missing required key 'tipo'.")
                        if "titulo" not in ch:
                            errors.append(f"modulos[{i}]['graficos'][{j}] missing required key 'titulo'.")
            
            # Validate tables
            if "tablas" in mod:
                if not isinstance(mod["tablas"], list):
                    errors.append(f"modulos[{i}]['tablas'] must be a list.")
                else:
                    for j, tbl in enumerate(mod["tablas"]):
                        if not isinstance(tbl, dict):
                            errors.append(f"modulos[{i}]['tablas'][{j}] must be a dict.")
                            continue
                        if "sql" not in tbl:
                            errors.append(f"modulos[{i}]['tablas'][{j}] missing required key 'sql'.")
    
    # Validate filters
    if "filtros_globales" in config and isinstance(config["filtros_globales"], list):
        for i, f in enumerate(config["filtros_globales"]):
            if not isinstance(f, dict):
                errors.append(f"filtros_globales[{i}] must be a dict.")
                continue
            if "nombre" not in f:
                errors.append(f"filtros_globales[{i}] missing required key 'nombre'.")
            if "columna" not in f:
                errors.append(f"filtros_globales[{i}] missing required key 'columna'.")
            if "tabla" not in f:
                errors.append(f"filtros_globales[{i}] missing required key 'tabla'.")
    
    return errors


def actualizar_ui_config(config: dict, config_path: Path | None = None) -> str:
    """Validate and save a complete ui_config.json structure.
    
    This is the main function for the MCP agent to update the dashboard
    configuration. It validates the structure, checks required keys, and
    saves the file. The UI will automatically pick up the changes.
    
    Expected structure:
    ```json
    {
      "titulo_pagina": "Dashboard",
      "brand_name": "Dashboard",
      "brand_sub": "",
      "brand_icon": "dashboard",
      "column_mapping": {"sales_sucursal": "branch", ...},
      "filtros_globales": [
        {"nombre": "branch", "columna": "branch", "tabla": "sales", "tipo": "select"}
      ],
      "modulos": [
        {
          "id": "dashboard",
          "nombre": "Executive Overview",
          "icono": "📊",
          "material_icon": "dashboard",
          "breadcrumbs": "HOME  /  DASHBOARD",
          "kpis": [
            {"icono": "payments", "label": "Total Sales", "sql": "...", "formato": "money"}
          ],
          "graficos": [
            {"tipo": "bar", "titulo": "Sales by Branch", "sql": "...", "x": "Branch", "y": "Sales"}
          ],
          "tablas": [
            {"titulo": "Recent Sales", "sql": "...", "columnas": [...]}
          ]
        }
      ],
      "sidebar_disclaimer": "",
      "footer": "",
      "empty_state": {
        "title": "No data to display",
        "desc": "Upload a CSV to get started.",
        "hint": ""
      }
    }
    ```
    
    Args:
        config: Complete ui_config.json structure as a dict.
        config_path: Optional custom path. Defaults to project root/ui_config.json.
    
    Returns:
        Status message with validation result and save confirmation.
    """
    target_path = config_path or _CONFIG_PATH
    
    # Validate structure
    errors = _validar_config(config)
    if errors:
        return "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
    
    # Add defaults for optional UI fields if missing
    if "titulo_pagina" not in config:
        config["titulo_pagina"] = "Dashboard"
    if "brand_name" not in config:
        config["brand_name"] = config.get("titulo_pagina", "Dashboard")
    if "brand_sub" not in config:
        config["brand_sub"] = ""
    if "brand_icon" not in config:
        config["brand_icon"] = "dashboard"
    if "sidebar_disclaimer" not in config:
        config["sidebar_disclaimer"] = ""
    if "footer" not in config:
        config["footer"] = ""
    if "empty_state" not in config:
        config["empty_state"] = {
            "title": "No data to display",
            "desc": "Upload a CSV to get started.",
            "hint": ""
        }
    
    # Save atomically: the UI may be reading the file at the same time, and a
    # half-written JSON would leave the dashboard without a config.
    target_path.parent.mkdir(parents=True, exist_ok=True)
    json_string = json.dumps(config, indent=2, ensure_ascii=False)
    tmp_path = target_path.with_name(target_path.name + ".tmp")
    tmp_path.write_text(json_string, encoding="utf-8")
    os.replace(tmp_path, target_path)
    
    # Summary
    n_modulos = len(config.get("modulos", []))
    n_filtros = len(config.get("filtros_globales", []))
    n_mappings = len(config.get("column_mapping", {}))
    n_kpis = sum(len(m.get("kpis", [])) for m in config.get("modulos", []))
    n_charts = sum(len(m.get("graficos", [])) for m in config.get("modulos", []))
    
    return (
        f"Config saved to {target_path.name}.\n"
        f"  - {n_mappings} column mappings\n"
        f"  - {n_filtros} global filters\n"
        f"  - {n_modulos} modules\n"
        f"  - {n_kpis} KPIs\n"
        f"  - {n_charts} charts\n"
    )


def cargar_config(config_path: Path | None = None) -> dict:
    """Load the current ui_config.json from disk.
    
    Args:
        config_path: Optional custom path. Defaults to project root/ui_config.json.
    
    Returns:
        Dict with the config, or empty dict if not found.
    """
    target_path = config_path or _CONFIG_PATH
    if not target_path.exists():
        return {}
    try:
        return json.loads(target_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
