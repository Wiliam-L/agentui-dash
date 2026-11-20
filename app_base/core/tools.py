"""Dynamic query engine — the bridge between ui_config.json and DuckDB.

Everything is driven by JSON configuration: SQL queries, KPIs, filters, charts.
This module executes queries defined in the JSON config and returns DataFrames
that the UI renders via `render_chart()`.

No hardcoded column names, no hardcoded queries — everything comes from the config.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import sqlglot
from sqlglot import exp

from .data import ejecutar

_logger = logging.getLogger("tools")

# --------------------------------------------------------------------------- #
# Query cache — avoids re-executing identical queries on every refresh
# --------------------------------------------------------------------------- #

_query_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_QUERY_CACHE_TTL = 60  # seconds


def _get_cached(sql: str) -> pd.DataFrame | None:
    """Return cached DataFrame if still valid, else None."""
    h = hashlib.md5(sql.encode()).hexdigest()
    entry = _query_cache.get(h)
    if entry is None:
        return None
    ts, df = entry
    if time.time() - ts > _QUERY_CACHE_TTL:
        _query_cache.pop(h, None)
        return None
    return df


def _set_cache(sql: str, df: pd.DataFrame) -> None:
    """Store a DataFrame in the cache."""
    h = hashlib.md5(sql.encode()).hexdigest()
    _query_cache[h] = (time.time(), df)


def clear_query_cache() -> None:
    """Clear the query cache (useful after data changes)."""
    _query_cache.clear()

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

def _col_name(node) -> str:
    """Safely extract a lowercase column name from a sqlglot node, stripping quotes."""
    val = node.this if hasattr(node, 'this') else node
    s = val if isinstance(val, str) else str(val)
    # Strip surrounding quotes that sqlglot may include
    s = s.strip('"').strip("'").strip("`")
    return s.lower()


def _extract_filter_columns(conditions_str: str) -> set[str]:
    """Extract column names referenced in filter conditions.

    Returns a lowercase set of column names (e.g. {'invoicedate', 'country'}).
    """
    cols: set[str] = set()
    cond_tree = sqlglot.parse_one(f"SELECT 1 WHERE {conditions_str}", read="duckdb")
    for col_node in cond_tree.find_all(exp.Column):
        cols.add(_col_name(col_node))
    return cols


def _walk_no_subqueries(node: exp.Expression):
    """Walk the AST but do NOT descend into Subquery or CTE nodes."""
    yield node
    for child in node.iter_expressions():
        if isinstance(child, (exp.Subquery, exp.CTE)):
            continue  # skip subqueries entirely
        yield from _walk_no_subqueries(child)


def _top_level_columns(select_tree: exp.Select) -> set[str]:
    """Return lowercase column names referenced ONLY in the top-level SELECT.

    This excludes columns inside subqueries/CTEs nested within this SELECT.
    """
    cols: set[str] = set()
    for node in _walk_no_subqueries(select_tree):
        if isinstance(node, exp.Column):
            cols.add(_col_name(node))
    return cols


def _table_columns(tree: exp.Expression, table_name: str | None = None) -> set[str]:
    """Return lowercase column names available in *tree*'s top-level SELECT."""
    if isinstance(tree, exp.Select):
        return _top_level_columns(tree)
    cols: set[str] = set()
    for col_node in tree.find_all(exp.Column):
        cols.add(_col_name(col_node))
    return cols


def _get_base_table(tree: exp.Expression) -> str | None:
    """Return the base table name from the top-level FROM clause, or None."""
    from_clause = tree.find(exp.From)
    if from_clause is None:
        return None
    table = from_clause.find(exp.Table)
    if table is None:
        return None
    return table.name


def _inject_filters_with_sqlglot(sql: str, conditions_str: str) -> str:
    """Inject filter conditions into a SQL query using sqlglot AST.

    This is the robust replacement for manual string manipulation. It:
    - Parses the SQL into an AST
    - Finds or creates a WHERE clause
    - Merges the new conditions with any existing WHERE using AND
    - Handles subqueries, CTEs, HAVING, etc. correctly
    - When the query uses a subquery/CTE and the filter columns don't exist
      in the outer query, injects the WHERE into the innermost subquery/CTE
      that references the base table.

    Args:
        sql: Original SQL query string.
        conditions_str: The filter conditions (without "WHERE" prefix).

    Returns:
        The modified SQL with filters injected.
    """
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")

        # Build the new condition expression from the conditions string
        cond_expr = sqlglot.parse_one(f"SELECT 1 WHERE {conditions_str}", read="duckdb")
        new_where = cond_expr.find(exp.Where)
        if new_where is None:
            return sql
        new_cond = new_where.this

        # Extract which columns the filters reference
        filter_cols = _extract_filter_columns(conditions_str)

        # Get the base table of the top-level SELECT
        base_table = _get_base_table(tree)

        # Check if filter columns are available in the top-level query
        top_cols = _table_columns(tree, base_table)

        if not filter_cols or filter_cols.issubset(top_cols):
            # Filter columns exist in the top-level — inject normally
            existing_where = tree.find(exp.Where)
            if existing_where is not None:
                merged = exp.And(this=existing_where.this, expression=new_cond)
                existing_where.set("this", merged)
            else:
                tree.set("where", exp.Where(this=new_cond))
            return tree.sql(dialect="duckdb")

        # Filter columns NOT in top-level — try to inject into subqueries/CTEs
        # that read from the same base table. If a subquery/CTE reads directly
        # from a table (e.g. FROM online_retail), assume all columns of that
        # table are available there.

        def _inject_into_select(sel: exp.Select) -> bool:
            """Try to inject the WHERE into *sel*. Return True if successful."""
            existing_where = sel.find(exp.Where)
            if existing_where is not None:
                merged = exp.And(this=existing_where.this, expression=new_cond)
                existing_where.set("this", merged)
            else:
                sel.set("where", exp.Where(this=new_cond))
            return True

        # First, try CTEs
        for cte in tree.find_all(exp.CTE):
            cte_select = cte.find(exp.Select)
            if cte_select is None:
                continue
            cte_table = _get_base_table(cte_select)
            if cte_table is not None:
                # CTE reads from a base table — inject here
                _inject_into_select(cte_select)
                return tree.sql(dialect="duckdb")
            cte_cols = _table_columns(cte_select, cte_table)
            if filter_cols.issubset(cte_cols):
                _inject_into_select(cte_select)
                return tree.sql(dialect="duckdb")

        # Then, try subqueries in FROM clause
        for subq in tree.find_all(exp.Subquery):
            subq_select = subq.find(exp.Select)
            if subq_select is None:
                continue
            subq_table = _get_base_table(subq_select)
            if subq_table is not None:
                # Subquery reads from a base table — inject here
                _inject_into_select(subq_select)
                return tree.sql(dialect="duckdb")
            subq_cols = _table_columns(subq_select, subq_table)
            if filter_cols.issubset(subq_cols):
                _inject_into_select(subq_select)
                return tree.sql(dialect="duckdb")

        # Fallback: inject at top-level anyway (may produce empty results,
        # but preserves backward compatibility)
        existing_where = tree.find(exp.Where)
        if existing_where is not None:
            merged = exp.And(this=existing_where.this, expression=new_cond)
            existing_where.set("this", merged)
        else:
            tree.set("where", exp.Where(this=new_cond))
        return tree.sql(dialect="duckdb")
    except Exception:
        # Fallback: if sqlglot fails, return original SQL (let DuckDB handle it)
        _logger.warning("sqlglot filter injection failed, falling back to original SQL")
        return sql


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

    # If no filters, use cache
    if not filtros_config or not filtros_valores:
        cached = _get_cached(sql)
        if cached is not None:
            return cached

    # If filters are provided, inject WHERE clause using sqlglot
    if filtros_config and filtros_valores:
        where, params = _build_where(filtros_config, filtros_valores)
        if where:
            # Extract the conditions from the WHERE clause (remove " WHERE " prefix)
            conditions = where[7:]  # Strip " WHERE " to get just the conditions

            # Use sqlglot for robust filter injection
            sql = _inject_filters_with_sqlglot(sql, conditions)

            # Execute with timing
            start = time.time()
            df = ejecutar(sql, params)
            elapsed = time.time() - start
            if elapsed > 2.0:
                _logger.warning(f"Slow query ({elapsed:.3f}s): {sql[:200]}")

            return df

    # No filters — use cache
    cached = _get_cached(sql)
    if cached is not None:
        return cached

    # Execute with timing
    start = time.time()
    df = ejecutar(sql)
    elapsed = time.time() - start
    if elapsed > 2.0:
        _logger.warning(f"Slow query ({elapsed:.3f}s): {sql[:200]}")

    _set_cache(sql, df)
    return df


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


def _validar_sql_en_config(config: dict) -> list[str]:
    """Validate all SQL queries in a config against sqlglot syntax.

    Args:
        config: Dict with ui_config.json structure.

    Returns:
        List of error strings. Empty list means all SQL is valid.
    """
    errors: list[str] = []

    def _check_sql(sql: str, label: str) -> None:
        try:
            sqlglot.parse_one(sql, read="duckdb")
        except Exception as e:
            errors.append(f"Invalid SQL in {label}: {e}")

    for i, mod in enumerate(config.get("modulos", [])):
        mod_name = mod.get("nombre", f"modulos[{i}]")
        for j, kpi in enumerate(mod.get("kpis", [])):
            sql = kpi.get("sql", "")
            label = f"KPI '{kpi.get('label', j)}' in '{mod_name}'"
            if sql:
                _check_sql(sql, label)
        for j, ch in enumerate(mod.get("graficos", [])):
            sql = ch.get("sql", "")
            label = f"Chart '{ch.get('titulo', j)}' in '{mod_name}'"
            if sql:
                _check_sql(sql, label)
        for j, tbl in enumerate(mod.get("tablas", [])):
            sql = tbl.get("sql", "")
            label = f"Table '{tbl.get('titulo', j)}' in '{mod_name}'"
            if sql:
                _check_sql(sql, label)

    return errors


def actualizar_ui_config(config: dict, config_path: Path | None = None) -> str:
    """Validate and save a complete ui_config.json structure.

    This is the main function for the MCP agent to update the dashboard
    configuration. It validates the structure, checks SQL syntax, creates
    a backup of the previous config, and saves the file atomically.
    The UI will automatically pick up the changes.

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

    # Validate all SQL queries
    sql_errors = _validar_sql_en_config(config)
    if sql_errors:
        return "SQL validation failed:\n" + "\n".join(f"  - {e}" for e in sql_errors)

    # Backup existing config before overwriting
    if target_path.exists():
        backup_path = target_path.with_suffix(".json.bak")
        try:
            import shutil
            shutil.copy2(target_path, backup_path)
            _logger.info(f"Config backed up to {backup_path}")
        except Exception as e:
            _logger.warning(f"Failed to backup config: {e}")

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

    # Clear query cache after config change
    clear_query_cache()

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
