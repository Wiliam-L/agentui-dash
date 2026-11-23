"""Inference utility: analyse a DataFrame sample and generate UI configuration.

Owns the ``_ROLES`` dictionary (column synonym knowledge) and uses it to detect
which physical CSV columns map to which logical roles.  The ``generate_ui_config()``
function produces a ``ui_config.json`` with ``column_mapping`` (role → physical
column name) and chart configs that use physical column names.

This is the function the MCP server will call to auto-generate dashboard layouts.
All SQL generated uses the actual table name provided by the caller — no hardcoded
table names like "sales", "inventory", or "customers".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Column role synonyms — the single source of truth for column detection
# --------------------------------------------------------------------------- #
_ROLES = {
    "sales": {
        "sucursal": ["branch", "sucursal", "store", "location", "tienda", "site", "sede", "local",
                      "shop", "outlet", "customer", "buyer", "region", "area", "zone", "zона",
                      "department", "departamento", "filial", "office", "oficina", "store_id",
                      "branch_id", "location_id", "site_id", "region_name", "area_name"],
        "fecha": ["date", "fecha", "fecha_venta", "sale_date", "transaction_date", "dia",
                  "year", "month", "year_month", "period", "periodo", "anio", "mes",
                  "timestamp", "datetime", "created_at", "order_date", "ship_date",
                  "delivery_date", "invoice_date", "fecha_factura", "fecha_entrega",
                  "fecha_registro", "registered_at", "updated_at", "time", "hora",
                  "date_time", "fecha_hora", "period_start", "period_end"],
        "categoria": ["product_category", "category", "categoria", "department", "grupo",
                      "seccion", "rubro", "product_type", "linea", "product", "item",
                      "tipo", "kind", "variety", "product_name", "item_name", "service",
                      "servicio", "class", "clase", "group", "familia", "brand", "marca",
                      "product_line", "linea_producto", "segment", "segmento"],
        "monto": ["total_usd", "total", "gross_total", "amount", "sales_amount", "revenue",
                  "total_amount", "monto", "importe", "gross", "venta", "ingreso",
                  "price", "unit_price", "price_per_unit", "costo_unitario",
                  "precio_total", "total_price", "net_sales", "neto", "subtotal",
                  "sales", "ventas", "income", "earnings", "turnover", "value", "valor",
                  "amount_usd", "amount_eur", "amount_gbp", "total_cost", "net_amount",
                  "discount_amount", "tax_amount", "profit", "ganancia", "benefit"],
        "cantidad": ["units_sold", "quantity", "qty", "units", "cantidad", "count", "num",
                     "numero", "piece_count", "volume", "volumen", "pieces", "piezas",
                     "items_sold", "num_items", "total_units", "ship_quantity", "ordered_qty"],
        "metodo": ["payment_method", "payment", "metodo_pago", "method", "payment_type", "pago",
                   "pay_type", "card_type", "cash_or_card", "transaction_type"],
        "turno": ["shift", "turno", "time_shift", "horario", "jornada", "shift_name",
                  "morning_afternoon", "time_period"],
        "cajero": ["cashier", "cashier_name", "vendedor", "employee", "seller", "cajero", "agente",
                    "salesperson", "rep", "representative", "user", "operator", "atendente",
                    "employee_name", "staff", "worker"],
        "invoice": ["invoice_id", "invoice", "order_id", "ticket_id", "factura", "order", "ticket",
                    "pedido", "transaction_id", "sale_id", "receipt", "recibo", "doc_number",
                    "document_id", "id_transaccion"],
    },
    "customers": {
        "id": ["customer_id", "id", "cliente_id", "cliente", "usuario", "user_id",
               "account_id", "member_id", "client_id", "person_id"],
        "nombre": ["name", "nombre", "customer_name", "full_name", "apellido", "first_name",
                   "last_name", "contact_name", "client_name", "person_name"],
        "genero": ["gender", "genero", "sex", "sexo", "gender_type"],
        "estado": ["state", "estado", "province", "region", "departamento", "provincia",
                   "country", "pais", "nation", "territory"],
        "ciudad": ["city", "ciudad", "town", "localidad", "municipality", "district"],
        "segmento": ["segment", "segmento", "tier", "loyalty_segment", "nivel", "level",
                     "customer_type", "client_type", "classification"],
        "canal": ["preferred_channel", "channel", "canal", "contact_channel", "medium",
                  "communication_channel", "source"],
        "activo": ["active", "activo", "is_active", "status", "active_status",
                   "account_status", "enabled"],
    },
    "inventory": {
        "sku": ["sku", "sku_id", "codigo", "product_code", "id", "clave", "cod",
                "barcode", "ean", "article", "reference", "item_code", "part_number",
                "material_number", "mpn"],
        "producto": ["product", "producto", "product_name", "item", "nombre", "descripcion",
                     "description", "item_name", "product_description"],
        "categoria": ["category", "categoria", "department", "rubro", "product_category",
                      "item_category", "group"],
        "marca": ["brand", "marca", "brand_name", "fabricante", "manufacturer", "maker",
                  "supplier", "proveedor"],
        "costo": ["cost_usd", "cost", "costo", "unit_cost", "coste", "purchase_price",
                  "wholesale_price", "base_cost"],
        "precio": ["price_usd", "price", "precio", "unit_price", "sale_price", "venta",
                   "retail_price", "list_price", "msrp"],
        "stock": ["current_stock", "stock", "qty", "quantity", "units", "stock_actual",
                  "existencia", "in_stock", "available", "disponible", "on_hand",
                  "inventory_qty", "stock_level"],
        "stock_min": ["min_stock", "min", "minimum_stock", "reorder_level", "stock_minimo",
                      "minimo", "umbral", "safety_stock", "reorder_point"],
        "estado_stock": ["stock_status", "status", "estado", "availability", "disponibilidad",
                         "stock_state", "inventory_status"],
    },
}


def _detect_physical_columns(df: pd.DataFrame, tipo: str) -> dict[str, str]:
    """Given a DataFrame and a table type, return {role: physical_column_name}.

    Iterates ``_ROLES[tipo]`` and matches each role's synonym list against
    the actual DataFrame column names (case-insensitive).
    """
    mapping: dict[str, str] = {}
    cols_lower = {str(c).lower().strip(): str(c) for c in df.columns}
    roles = _ROLES.get(tipo, {})
    used: set[str] = set()

    for role, aliases in roles.items():
        for alias in aliases:
            alias_lower = alias.lower().strip()
            if alias_lower in cols_lower and alias_lower not in used:
                mapping[role] = cols_lower[alias_lower]
                used.add(alias_lower)
                break
    return mapping


def _count_roles_matched(df: pd.DataFrame, tipo: str) -> int:
    """Count how many roles from _ROLES[tipo] match columns in the DataFrame."""
    mapping = _detect_physical_columns(df, tipo)
    return len(mapping)


def _detect_type(df: pd.DataFrame) -> str | None:
    """Detect whether a DataFrame matches a known role set (sales, customers, inventory).

    Uses _ROLES as the single source of truth: for each table type, counts how
    many roles have a matching column. The type with the most matches wins.
    A minimum threshold of 2 matched roles is required to avoid false positives.
    """
    best_type: str | None = None
    best_count = 0
    for tipo in _ROLES:
        mapping = _detect_physical_columns(df, tipo)
        if len(mapping) > best_count:
            best_count = len(mapping)
            best_type = tipo
    if best_count >= 2:
        return best_type
    return None


def _classify_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Classify DataFrame columns into categories by heuristic analysis.

    Returns a dict with keys: 'categorical', 'numeric', 'date', 'high_cardinality'.
    This is used by the generic module generator when no predefined role set matches.
    """
    categorical: list[str] = []
    numeric: list[str] = []
    date_cols: list[str] = []
    high_card: list[str] = []

    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_datetime64_any_dtype(dtype):
            date_cols.append(col)
        elif pd.api.types.is_numeric_dtype(dtype):
            unique_count = df[col].nunique()
            if unique_count <= 15 and unique_count < len(df) * 0.1:
                categorical.append(col)
            else:
                numeric.append(col)
        else:
            unique_count = df[col].nunique()
            if unique_count <= 20:
                categorical.append(col)
            else:
                high_card.append(col)

    return {
        "categorical": categorical,
        "numeric": numeric,
        "date": date_cols,
        "high_cardinality": high_card,
    }


def _generate_generic_modules(
    df: pd.DataFrame, table_name: str
) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Generate a generic dashboard module from ANY DataFrame using heuristics.

    When no predefined role set (sales/customers/inventory) matches, this function
    analyzes the DataFrame columns and creates:
    - KPIs for each numeric column (SUM, AVG, COUNT)
    - Bar charts for each categorical × numeric combination
    - Pie charts for categorical columns with few unique values
    - Line charts for date × numeric combinations
    - A data preview table
    - Filters for categorical and date columns

    Args:
        df: Sample DataFrame (first ~100 rows).
        table_name: DuckDB table name for SQL generation.

    Returns:
        Tuple of (modules, global_filters, column_mapping).
    """
    t = table_name
    classified = _classify_columns(df)
    cat_cols = classified["categorical"]
    num_cols = classified["numeric"]
    date_cols = classified["date"]

    column_mapping: dict[str, str] = {}
    filters: list[dict] = []
    kpis: list[dict] = []
    charts: list[dict] = []

    # --- KPIs: count rows + SUM/AVG for each numeric column ---
    kpis.append({
        "icono": "table_rows",
        "label": "Total Records",
        "sql": f"SELECT COUNT(*) AS v FROM {t}",
        "formato": "int",
        "color": "#246bfd",
    })

    for nc in num_cols:
        label = nc.replace("_", " ").title()
        kpis.append({
            "icono": "calculate",
            "label": f"Total {label}",
            "sql": f"SELECT COALESCE(SUM({_q(nc)}), 0) AS v FROM {t}",
            "formato": "money",
            "color": "#12b76a",
        })
        kpis.append({
            "icono": "trending_up",
            "label": f"Avg {label}",
            "sql": f"SELECT COALESCE(AVG({_q(nc)}), 0) AS v FROM {t}",
            "formato": "money",
            "color": "#f59e0b",
        })
        column_mapping[f"numeric_{nc}"] = nc

    # --- Charts: categorical × numeric → bar ---
    for cc in cat_cols:
        for nc in num_cols:
            cat_label = cc.replace("_", " ").title()
            num_label = nc.replace("_", " ").title()
            charts.append({
                "tipo": "bar",
                "titulo": f"{num_label} by {cat_label}",
                "sub": f"Sum of {nc} grouped by {cc}",
                "icono": "bar_chart",
                "sql": f"SELECT {_q(cc)} AS Category, COALESCE(SUM({_q(nc)}), 0) AS Total FROM {t} WHERE {_q(cc)} IS NOT NULL GROUP BY {_q(cc)} ORDER BY Total DESC",
                "x": "Category",
                "y": "Total",
                "alto": 380,
                "col_izq": 1.25,
            })
            column_mapping[f"categorical_{cc}"] = cc

    # --- Charts: categorical with few values → pie ---
    for cc in cat_cols:
        unique_count = df[cc].nunique()
        if unique_count <= 8 and unique_count >= 2 and num_cols:
            nc = num_cols[0]
            cat_label = cc.replace("_", " ").title()
            num_label = nc.replace("_", " ").title()
            charts.append({
                "tipo": "pie",
                "titulo": f"Share of {num_label} by {cat_label}",
                "sub": f"Distribution of {nc} across {cc}",
                "icono": "pie_chart",
                "sql": f"SELECT {_q(cc)} AS Category, COALESCE(SUM({_q(nc)}), 0) AS Total FROM {t} WHERE {_q(cc)} IS NOT NULL GROUP BY {_q(cc)} ORDER BY Total DESC",
                "columna": "Category",
                "valores": "Total",
                "alto": 380,
                "col_izq": 1,
            })

    # --- Charts: date × numeric → line ---
    for dc in date_cols:
        for nc in num_cols:
            date_label = dc.replace("_", " ").title()
            num_label = nc.replace("_", " ").title()
            charts.append({
                "tipo": "line",
                "titulo": f"{num_label} over {date_label}",
                "sub": f"Trend of {nc} over time",
                "icono": "show_chart",
                "sql": f"SELECT {_q(dc)} AS Date, COALESCE(SUM({_q(nc)}), 0) AS Total FROM {t} WHERE {_q(dc)} IS NOT NULL GROUP BY {_q(dc)} ORDER BY Date",
                "x": "Date",
                "y": "Total",
                "alto": 350,
            })
            column_mapping[f"date_{dc}"] = dc

    # --- Filters for categorical columns ---
    for cc in cat_cols:
        unique_count = df[cc].nunique()
        if unique_count <= 30:
            filter_type = "multiselect" if unique_count > 5 else "select"
            filters.append({
                "nombre": cc,
                "etiqueta": cc.replace("_", " ").title(),
                "columna": cc,
                "tabla": t,
                "tipo": filter_type,
            })

    # --- Filters for date columns ---
    for dc in date_cols:
        filters.append({
            "nombre": dc,
            "etiqueta": dc.replace("_", " ").title(),
            "columna": dc,
            "tabla": t,
            "tipo": "date_range",
        })

    # --- Data preview table ---
    tables: list[dict] = [{
        "titulo": "Data Preview",
        "sub": "First 100 rows of the dataset",
        "icono": "table_chart",
        "sql": f"SELECT * FROM {t} LIMIT 100",
        "limite": 100,
        "altura": 400,
    }]

    # Build module
    modules: list[dict] = [{
        "id": "explorer",
        "nombre": "Data Explorer",
        "icono": "search",
        "descripcion": "Auto-generated dashboard — explore your data with KPIs, charts, and filters.",
        "material_icon": "insights",
        "breadcrumbs": "HOME  /  DATA EXPLORER",
        "kpis": kpis,
        "graficos": charts,
        "tablas": tables,
    }]

    return modules, filters, column_mapping


def generate_ui_config(df_head: pd.DataFrame, table_name: str = "data") -> dict[str, Any]:
    """Analyse *df_head* (first ~100 rows) and return a full UI config dictionary.

    Uses ``_ROLES`` to detect physical columns, builds ``column_mapping``,
    and generates the complete JSON structure with:
    - ``filtros_globales``: dynamic filter definitions
    - ``modulos``: each with ``kpis`` (SQL queries), ``graficos`` (SQL + chart type),
      and optionally ``tablas`` (SQL tables)
    - ``column_mapping``: role → physical column name

    If no predefined role set matches (threshold < 2), falls back to a generic
    module that auto-detects numeric, categorical, and date columns to create
    KPIs, charts, and filters — ensuring the dashboard is never empty.

    All SQL uses *table_name* (provided by the caller) — no hardcoded table names.

    Args:
        df_head: First ~100 rows of the data to analyze.
        table_name: DuckDB table name to use in all generated SQL (default: "data").

    Returns:
        A dict ready to be written as ui_config.json.
    """
    tipo = _detect_type(df_head)

    if tipo is not None:
        # Known role set matched — use specialized generators
        col_map = _detect_physical_columns(df_head, tipo)

        column_mapping: dict[str, str] = {}
        for role, col in col_map.items():
            column_mapping[f"{tipo}_{role}"] = col

        filters = _generate_filters(tipo, col_map, table_name)
        modules = _generate_modules(tipo, col_map, table_name)
    else:
        # No known role set matched — use generic heuristic-based generator
        modules, filters, column_mapping = _generate_generic_modules(df_head, table_name)

    # Build the full config
    config: dict[str, Any] = {
        "titulo_pagina": "Dashboard",
        "brand_name": "Dashboard",
        "brand_sub": "",
        "brand_logo": "ageui-logo.png",
        "brand_icon": "dashboard",
        "column_mapping": column_mapping,
        "filtros_globales": filters,
        "modulos": modules,
        "sidebar_disclaimer": "",
        "footer": "",
        "empty_state": {
            "title": "No data to display",
            "description": "Upload your data files from the side panel to start analyzing.",
            "hint": "",
        },
    }
    return config


def _generate_filters(tipo: str, col_map: dict[str, str], table_name: str) -> list[dict]:
    """Generate filter definitions based on detected columns.

    All labels are derived from the actual physical column names — no hardcoded
    business terms like "Branch" or "Product categories".

    Args:
        tipo: Detected role set (e.g. "sales", "customers", "inventory").
        col_map: {role: physical_column} mapping.
        table_name: DuckDB table name for filter SQL.
    """
    filters: list[dict] = []

    if tipo == "sales":
        branch = col_map.get("sucursal")
        date = col_map.get("fecha")
        cat = col_map.get("categoria")

        if branch:
            filters.append({
                "nombre": branch,
                "etiqueta": branch.replace("_", " ").title(),
                "columna": branch,
                "tabla": table_name,
                "tipo": "select",
                "todos_label": f"All {branch.replace('_', ' ').lower()}",
            })
        if date:
            filters.append({
                "nombre": date,
                "etiqueta": date.replace("_", " ").title(),
                "columna": date,
                "tabla": table_name,
                "tipo": "date_range",
            })
        if cat:
            filters.append({
                "nombre": cat,
                "etiqueta": cat.replace("_", " ").title(),
                "columna": cat,
                "tabla": table_name,
                "tipo": "multiselect",
            })

    elif tipo == "customers":
        seg = col_map.get("segmento")
        state = col_map.get("estado")
        channel = col_map.get("canal")
        if seg:
            filters.append({"nombre": seg, "etiqueta": seg.replace("_", " ").title(), "columna": seg, "tabla": table_name, "tipo": "select", "todos_label": f"All {seg.replace('_', ' ').lower()}"})
        if state:
            filters.append({"nombre": state, "etiqueta": state.replace("_", " ").title(), "columna": state, "tabla": table_name, "tipo": "select", "todos_label": f"All {state.replace('_', ' ').lower()}"})
        if channel:
            filters.append({"nombre": channel, "etiqueta": channel.replace("_", " ").title(), "columna": channel, "tabla": table_name, "tipo": "multiselect"})

    elif tipo == "inventory":
        cat = col_map.get("categoria")
        brand = col_map.get("marca")
        status = col_map.get("estado_stock")
        if cat:
            filters.append({"nombre": cat, "etiqueta": cat.replace("_", " ").title(), "columna": cat, "tabla": table_name, "tipo": "multiselect"})
        if brand:
            filters.append({"nombre": brand, "etiqueta": brand.replace("_", " ").title(), "columna": brand, "tabla": table_name, "tipo": "select", "todos_label": f"All {brand.replace('_', ' ').lower()}"})
        if status:
            filters.append({"nombre": status, "etiqueta": status.replace("_", " ").title(), "columna": status, "tabla": table_name, "tipo": "select", "todos_label": f"All {status.replace('_', ' ').lower()}"})

    return filters


def _generate_modules(tipo: str, col_map: dict[str, str], table_name: str) -> list[dict]:
    """Generate module configs with KPIs, charts, and tables based on detected columns.

    Args:
        tipo: Detected role set (e.g. "sales", "customers", "inventory").
        col_map: {role: physical_column} mapping.
        table_name: DuckDB table name for all generated SQL.
    """
    modules: list[dict] = []

    if tipo == "sales":
        modules.extend(_generate_sales_modules(col_map, table_name))
    elif tipo == "inventory":
        modules.extend(_generate_inventory_modules(col_map, table_name))
    elif tipo == "customers":
        modules.extend(_generate_customers_modules(col_map, table_name))

    return modules


def _q(col: str) -> str:
    """Quote a column name for SQL, escaping embedded double quotes."""
    return '"' + str(col).replace('"', '""') + '"'


def _generate_sales_modules(col_map: dict[str, str], table_name: str) -> list[dict]:
    """Generate dashboard and operations modules for sales-like data.

    All labels, titles, and descriptions are derived from the actual physical
    column names — no hardcoded business terms.

    Args:
        col_map: {role: physical_column} mapping.
        table_name: DuckDB table name for all generated SQL.
    """
    branch = col_map.get("sucursal")
    date = col_map.get("fecha")
    cat = col_map.get("categoria")
    amount = col_map.get("monto")
    method = col_map.get("metodo")
    shift = col_map.get("turno")
    cashier = col_map.get("cajero")

    modules: list[dict] = []
    t = table_name

    # Helper: human-readable label from column name
    def _lbl(col: str) -> str:
        return col.replace("_", " ").title()

    amount_lbl = _lbl(amount) if amount else "Amount"
    branch_lbl = _lbl(branch) if branch else "Group"
    cat_lbl = _lbl(cat) if cat else "Category"
    method_lbl = _lbl(method) if method else "Method"
    shift_lbl = _lbl(shift) if shift else "Shift"
    cashier_lbl = _lbl(cashier) if cashier else "Person"

    # Avoid "Total Total X" when column already contains "total"
    amount_sum_label = amount_lbl if amount_lbl.lower().startswith("total") else f"Total {amount_lbl}"

    # Dashboard module
    dashboard_kpis: list[dict] = []
    if amount:
        dashboard_kpis.append({
            "icono": "payments",
            "label": amount_sum_label,
            "sql": f"SELECT COALESCE(SUM({_q(amount)}), 0) AS v FROM {t}",
            "formato": "money",
            "color": "#246bfd",
        })
        dashboard_kpis.append({
            "icono": "receipt_long",
            "label": "Records",
            "sql": f"SELECT COUNT(*) AS v FROM {t}",
            "formato": "int",
            "sub_label": "total records",
            "color": "#12b76a",
        })
        dashboard_kpis.append({
            "icono": "point_of_sale",
            "label": f"Avg {amount_lbl}",
            "sql": f"SELECT COALESCE(AVG({_q(amount)}), 0) AS v FROM {t}",
            "formato": "money",
            "sub_label": f"average {amount_lbl.lower()} per record",
            "color": "#f59e0b",
        })

    if branch and dashboard_kpis:
        dashboard_kpis[0]["sub_sql"] = f"SELECT COUNT(DISTINCT {_q(branch)}) AS v FROM {t}"
        dashboard_kpis[0]["sub_suffix"] = f" {branch_lbl.lower()}s"

    if cat and amount:
        dashboard_kpis.append({
            "icono": "category",
            "label": f"Top {cat_lbl}",
            "sql": f"SELECT {_q(cat)} AS v FROM {t} WHERE {_q(cat)} IS NOT NULL GROUP BY {_q(cat)} ORDER BY COALESCE(SUM({_q(amount)}), 0) DESC LIMIT 1",
            "formato": "str",
            "sub_sql": f"SELECT COUNT(*) AS v FROM {t} WHERE {_q(cat)} = (SELECT {_q(cat)} FROM {t} WHERE {_q(cat)} IS NOT NULL GROUP BY {_q(cat)} ORDER BY COALESCE(SUM({_q(amount)}), 0) DESC LIMIT 1)",
            "sub_suffix": f" {amount_lbl.lower()} records",
            "color": "#8b5cf6",
        })

    dashboard_charts: list[dict] = []
    if branch and amount:
        dashboard_charts.append({
            "tipo": "bar",
            "titulo": f"{amount_lbl} by {branch_lbl}",
            "sub": f"Total {amount_lbl.lower()} by {branch_lbl.lower()}",
            "icono": "storefront",
            "sql": f"SELECT {_q(branch)} AS {branch_lbl}, COALESCE(SUM({_q(amount)}), 0) AS Total FROM {t} WHERE {_q(branch)} IS NOT NULL GROUP BY {_q(branch)} ORDER BY Total DESC",
            "x": branch_lbl,
            "y": "Total",
            "alto": 380,
            "col_izq": 1.25,
        })
    if cat and amount:
        dashboard_charts.append({
            "tipo": "pie",
            "titulo": f"Share of {amount_lbl} by {cat_lbl}",
            "sub": f"{amount_lbl.lower()} share per {cat_lbl.lower()}",
            "icono": "pie_chart",
            "sql": f"SELECT {_q(cat)} AS {cat_lbl}, COALESCE(SUM({_q(amount)}), 0) AS Total FROM {t} WHERE {_q(cat)} IS NOT NULL GROUP BY {_q(cat)} ORDER BY Total DESC",
            "columna": cat_lbl,
            "valores": "Total",
            "alto": 380,
            "col_izq": 1,
        })

    modules.append({
        "id": "overview",
        "nombre": "Overview",
        "icono": "dashboard",
        "descripcion": f"Summary of {amount_lbl.lower()} data.",
        "material_icon": "dashboard",
        "breadcrumbs": "HOME  /  OVERVIEW",
        "kpis": dashboard_kpis,
        "graficos": dashboard_charts,
    })

    # Operations module (only if there are operational columns)
    ops_kpis: list[dict] = []
    if shift:
        ops_kpis.append({
            "icono": "schedule",
            "label": f"{shift_lbl} Count",
            "sql": f"SELECT COUNT(DISTINCT {_q(shift)}) AS v FROM {t}",
            "formato": "int",
            "sub_label": f"distinct {shift_lbl.lower()} values",
            "color": "#246bfd",
        })
    if cashier:
        ops_kpis.append({
            "icono": "badge",
            "label": f"Unique {cashier_lbl}",
            "sql": f"SELECT COUNT(DISTINCT {_q(cashier)}) AS v FROM {t}",
            "formato": "int",
            "sub_label": f"registered {cashier_lbl.lower()}",
            "color": "#12b76a",
        })
    if method:
        ops_kpis.append({
            "icono": "credit_card",
            "label": f"{method_lbl} Count",
            "sql": f"SELECT COUNT(DISTINCT {_q(method)}) AS v FROM {t}",
            "formato": "int",
            "sub_label": f"distinct {method_lbl.lower()}",
            "color": "#f59e0b",
        })
        if amount:
            ops_kpis.append({
                "icono": "payments",
                "label": f"Top {method_lbl}",
                "sql": f"SELECT {_q(method)} AS v FROM {t} WHERE {_q(method)} IS NOT NULL GROUP BY {_q(method)} ORDER BY COALESCE(SUM({_q(amount)}), 0) DESC LIMIT 1",
                "formato": "str",
                "sub_sql": f"SELECT COALESCE(SUM({_q(amount)}), 0) AS v FROM {t}",
                "sub_prefix": "$",
                "sub_suffix": f" {amount_lbl.lower()} total",
                "color": "#8b5cf6",
            })

    ops_charts: list[dict] = []
    if shift and amount:
        ops_charts.append({
            "tipo": "bar",
            "titulo": f"{amount_lbl} by {shift_lbl}",
            "sub": f"{amount_lbl.lower()} by {shift_lbl.lower()}",
            "icono": "schedule",
            "sql": f"SELECT {_q(shift)} AS {shift_lbl}, COALESCE(SUM({_q(amount)}), 0) AS Total, COUNT(*) AS Records FROM {t} WHERE {_q(shift)} IS NOT NULL GROUP BY {_q(shift)} ORDER BY Total",
            "x": shift_lbl,
            "y": "Total",
            "alto": 350,
            "col_izq": 1.15,
        })
    if method and amount:
        ops_charts.append({
            "tipo": "pie",
            "titulo": f"{method_lbl} Distribution",
            "sub": f"{amount_lbl.lower()} by {method_lbl.lower()}",
            "icono": "credit_card",
            "sql": f"SELECT {_q(method)} AS {method_lbl}, COALESCE(SUM({_q(amount)}), 0) AS Total, COUNT(*) AS Records FROM {t} WHERE {_q(method)} IS NOT NULL GROUP BY {_q(method)} ORDER BY Total DESC",
            "columna": method_lbl,
            "valores": "Total",
            "alto": 350,
            "col_izq": 1,
        })
    if cashier and amount:
        ops_charts.append({
            "tipo": "bar_h",
            "titulo": f"{cashier_lbl} Performance",
            "sub": f"Top {cashier_lbl.lower()} by {amount_lbl.lower()}",
            "icono": "person_pin",
            "sql": f"SELECT {_q(cashier)} AS {cashier_lbl}, COUNT(*) AS Records, COALESCE(SUM({_q(amount)}), 0) AS Total, COALESCE(AVG({_q(amount)}), 0) AS AvgVal FROM {t} WHERE {_q(cashier)} IS NOT NULL GROUP BY {_q(cashier)} ORDER BY Total DESC LIMIT 12",
            "x": "Total",
            "y": cashier_lbl,
            "alto": 420,
        })
    if shift and method and amount:
        ops_charts.append({
            "tipo": "heatmap",
            "titulo": f"{shift_lbl} & {method_lbl} Cross Analysis",
            "sub": f"{method_lbl.lower()} per {shift_lbl.lower()}",
            "icono": "table_chart",
            "sql": f"SELECT {_q(shift)} AS {shift_lbl}, {_q(method)} AS {method_lbl}, COALESCE(SUM({_q(amount)}), 0) AS Total FROM {t} WHERE {_q(shift)} IS NOT NULL AND {_q(method)} IS NOT NULL GROUP BY {_q(shift)}, {_q(method)}",
            "x": shift_lbl,
            "y": method_lbl,
            "valores": "Total",
            "alto": 320,
        })

    if ops_kpis or ops_charts:
        modules.append({
            "id": "details",
            "nombre": "Details",
            "icono": "insights",
            "descripcion": f"Detailed breakdown by {', '.join(lbl for lbl in [shift_lbl, cashier_lbl, method_lbl] if lbl != 'Shift' or shift)}.",
            "material_icon": "insights",
            "breadcrumbs": "HOME  /  DETAILS",
            "kpis": ops_kpis,
            "graficos": ops_charts,
        })

    return modules


def _generate_inventory_modules(col_map: dict[str, str], table_name: str) -> list[dict]:
    """Generate inventory module.

    All labels are derived from the actual physical column names.

    Args:
        col_map: {role: physical_column} mapping.
        table_name: DuckDB table name for all generated SQL.
    """
    status = col_map.get("estado_stock")
    cat = col_map.get("categoria")
    brand = col_map.get("marca")
    price = col_map.get("precio")
    cost = col_map.get("costo")
    stock = col_map.get("stock")
    stock_min = col_map.get("stock_min")
    sku = col_map.get("sku")

    t = table_name

    def _lbl(col: str) -> str:
        return col.replace("_", " ").title()

    stock_lbl = _lbl(stock) if stock else "Stock"
    stock_min_lbl = _lbl(stock_min) if stock_min else "Min Stock"
    status_lbl = _lbl(status) if status else "Status"
    cat_lbl = _lbl(cat) if cat else "Category"
    brand_lbl = _lbl(brand) if brand else "Brand"
    price_lbl = _lbl(price) if price else "Price"
    cost_lbl = _lbl(cost) if cost else "Cost"
    sku_lbl = _lbl(sku) if sku else "SKU"

    kpis: list[dict] = []
    kpis.append({
        "icono": "inventory_2",
        "label": "Total Items",
        "sql": f"SELECT COUNT(*) AS v FROM {t}",
        "formato": "int",
        "color": "#246bfd",
    })
    if sku:
        kpis[0]["sub_sql"] = f"SELECT COUNT(DISTINCT {_q(sku)}) AS v FROM {t}"
        kpis[0]["sub_suffix"] = f" unique {sku_lbl.lower()}"

    if stock:
        kpis.append({
            "icono": "box",
            "label": f"Total {stock_lbl}",
            "sql": f"SELECT COALESCE(SUM({_q(stock)}), 0) AS v FROM {t}",
            "formato": "int",
            "sub_label": f"total {stock_lbl.lower()} units",
            "color": "#12b76a",
        })
    if stock and stock_min:
        kpis.append({
            "icono": "warning",
            "label": "Below Minimum",
            "sql": f"SELECT SUM(CASE WHEN {_q(stock)} < {_q(stock_min)} THEN 1 ELSE 0 END) AS v FROM {t}",
            "formato": "int",
            "sub_label": f"items below {stock_min_lbl.lower()}",
            "color": "#f59e0b",
        })
        kpis.append({
            "icono": "block",
            "label": "Out of Stock",
            "sql": f"SELECT SUM(CASE WHEN {_q(stock)} <= 0 THEN 1 ELSE 0 END) AS v FROM {t}",
            "formato": "int",
            "sub_label": f"zero {stock_lbl.lower()} units",
            "color": "#ef4444",
        })

    charts: list[dict] = []
    if status:
        charts.append({
            "tipo": "bar_h",
            "titulo": f"{status_lbl} Distribution",
            "sub": f"Items by {status_lbl.lower()}",
            "icono": "inventory",
            "sql": f"SELECT {_q(status)} AS {status_lbl}, COUNT(*) AS Count FROM {t} WHERE {_q(status)} IS NOT NULL GROUP BY {_q(status)} ORDER BY Count",
            "x": "Count",
            "y": status_lbl,
            "alto": 340,
            "col_izq": 1.15,
        })
    if cat and price and cost:
        charts.append({
            "tipo": "bar_h",
            "titulo": f"Margin by {cat_lbl}",
            "sub": f"Average {price_lbl.lower()} minus {cost_lbl.lower()} by {cat_lbl.lower()}",
            "icono": "percent",
            "sql": f"SELECT {_q(cat)} AS {cat_lbl}, COALESCE(AVG({_q(price)} - {_q(cost)}), 0) AS avg_margin, COUNT(*) AS Count FROM {t} WHERE {_q(cat)} IS NOT NULL GROUP BY {_q(cat)} ORDER BY avg_margin",
            "x": "avg_margin",
            "y": cat_lbl,
            "alto": 340,
            "col_izq": 1,
        })
    if brand and price and cost and stock:
        charts.append({
            "tipo": "scatter",
            "titulo": f"Margin vs {stock_lbl} by {brand_lbl}",
            "sub": f"Margin % vs {stock_lbl.lower()} by {brand_lbl.lower()}",
            "icono": "storefront",
            "sql": f"SELECT {_q(brand)} AS {brand_lbl}, COALESCE(AVG(({_q(price)} - {_q(cost)}) / NULLIF({_q(price)}, 0)) * 100, 0) AS Margin_pct, COALESCE(SUM({_q(stock)}), 0) AS Total FROM {t} WHERE {_q(brand)} IS NOT NULL GROUP BY {_q(brand)} ORDER BY Total DESC",
            "x": "Total",
            "y": "Margin_pct",
            "color": brand_lbl,
            "alto": 400,
        })

    tables: list[dict] = []
    if stock and stock_min:
        tables.append({
            "titulo": f"Items Below {stock_min_lbl}",
            "sub": f"Where {stock_lbl.lower()} is less than {stock_min_lbl.lower()}",
            "icono": "warning",
            "sql": f"SELECT * FROM {t} WHERE {_q(stock)} < {_q(stock_min)} ORDER BY {_q(stock)}",
            "limite": 200,
            "altura": 360,
        })

    return [{
        "id": "inventory",
        "nombre": "Inventory",
        "icono": "inventory_2",
        "descripcion": f"{stock_lbl} levels and margin analysis.",
        "material_icon": "inventory_2",
        "breadcrumbs": "HOME  /  INVENTORY",
        "kpis": kpis,
        "graficos": charts,
        "tablas": tables,
    }]


def _generate_customers_modules(col_map: dict[str, str], table_name: str) -> list[dict]:
    """Generate customers module.

    All labels are derived from the actual physical column names.

    Args:
        col_map: {role: physical_column} mapping.
        table_name: DuckDB table name for all generated SQL.
    """
    seg = col_map.get("segmento")
    active = col_map.get("activo")
    state = col_map.get("estado")
    channel = col_map.get("canal")

    t = table_name

    def _lbl(col: str) -> str:
        return col.replace("_", " ").title()

    seg_lbl = _lbl(seg) if seg else "Segment"
    active_lbl = _lbl(active) if active else "Status"
    state_lbl = _lbl(state) if state else "Region"
    channel_lbl = _lbl(channel) if channel else "Channel"

    kpis: list[dict] = [
        {
            "icono": "groups",
            "label": "Total Records",
            "sql": f"SELECT COUNT(*) AS v FROM {t}",
            "formato": "int",
            "sub_label": "total records",
            "color": "#246bfd",
        },
    ]
    if active:
        kpis.append({
            "icono": "verified_user",
            "label": f"Active {active_lbl}",
            "sql": f"SELECT COUNT(*) AS v FROM {t} WHERE TRY_CAST({_q(active)} AS BOOLEAN)",
            "formato": "int",
            "sub_sql": f"SELECT COUNT(*) AS v FROM {t} WHERE TRY_CAST({_q(active)} AS BOOLEAN)",
            "sub_total_sql": f"SELECT COUNT(*) AS v FROM {t}",
            "sub_format": "percent",
            "sub_suffix": "% of total",
            "color": "#12b76a",
        })
        kpis.append({
            "icono": "block",
            "label": f"Inactive {active_lbl}",
            "sql": f"SELECT COUNT(*) AS v FROM {t} WHERE NOT TRY_CAST({_q(active)} AS BOOLEAN)",
            "formato": "int",
            "sub_label": f"inactive {active_lbl.lower()}",
            "color": "#f59e0b",
        })
    if state:
        kpis.append({
            "icono": "public",
            "label": f"Unique {state_lbl}",
            "sql": f"SELECT COUNT(DISTINCT {_q(state)}) AS v FROM {t}",
            "formato": "int",
            "sub_sql": f"SELECT COUNT(*) AS v FROM {t}",
            "sub_suffix": f" {state_lbl.lower()} records",
            "color": "#8b5cf6",
        })

    charts: list[dict] = []
    if seg:
        charts.append({
            "tipo": "bar_h",
            "titulo": f"Records by {seg_lbl}",
            "sub": f"Distribution across {seg_lbl.lower()}",
            "icono": "segment",
            "sql": f"SELECT {_q(seg)} AS {seg_lbl}, COUNT(*) AS Count FROM {t} WHERE {_q(seg)} IS NOT NULL GROUP BY {_q(seg)} ORDER BY Count DESC",
            "x": "Count",
            "y": seg_lbl,
            "alto": 340,
            "col_izq": 1.15,
        })
    if active:
        charts.append({
            "tipo": "pie",
            "titulo": f"{active_lbl} Distribution",
            "sub": f"Active vs inactive {active_lbl.lower()}",
            "icono": "toggle_on",
            "sql": f"SELECT (TRY_CAST({_q(active)} AS BOOLEAN)) AS Status, COUNT(*) AS Count FROM {t} GROUP BY Status",
            "columna": "Status",
            "valores": "Count",
            "alto": 340,
            "col_izq": 1,
        })
    if seg and channel:
        charts.append({
            "tipo": "bar_grouped",
            "titulo": f"{channel_lbl} by {seg_lbl}",
            "sub": f"{channel_lbl.lower()} crossed with {seg_lbl.lower()}",
            "icono": "call_split",
            "sql": f"SELECT {_q(seg)} AS {seg_lbl}, {_q(channel)} AS {channel_lbl}, COUNT(*) AS Count FROM {t} WHERE {_q(seg)} IS NOT NULL AND {_q(channel)} IS NOT NULL GROUP BY {_q(seg)}, {_q(channel)}",
            "x": channel_lbl,
            "y": "Count",
            "color": seg_lbl,
            "alto": 380,
        })
    if state and channel:
        charts.append({
            "tipo": "bar_stacked",
            "titulo": f"{state_lbl} by {channel_lbl}",
            "sub": f"Records per {state_lbl.lower()} by {channel_lbl.lower()}",
            "icono": "public",
            "sql": f"SELECT {_q(state)} AS {state_lbl}, {_q(channel)} AS {channel_lbl}, COUNT(*) AS Count FROM {t} WHERE {_q(state)} IS NOT NULL AND {_q(channel)} IS NOT NULL GROUP BY {_q(state)}, {_q(channel)}",
            "x": state_lbl,
            "y": "Count",
            "color": channel_lbl,
            "alto": 380,
            "top_n": 8,
        })

    return [{
        "id": "contacts",
        "nombre": "Contacts",
        "icono": "groups",
        "descripcion": f"Records segmentation by {', '.join(lbl for lbl in [seg_lbl, state_lbl, channel_lbl] if lbl not in ('Segment', 'Region', 'Channel')) or 'available columns'}.",
        "material_icon": "groups",
        "breadcrumbs": "HOME  /  CONTACTS",
        "kpis": kpis,
        "graficos": charts,
    }]


def generate_and_save(df_head: pd.DataFrame, output_path: str | None = None, table_name: str = "data") -> str:
    """Generate config from *df_head* and write to ``ui_config.json``.

    Args:
        df_head: First ~100 rows of the data to analyze.
        output_path: Optional output file path.
        table_name: DuckDB table name to use in all generated SQL.

    Returns:
        The absolute path of the written file.
    """
    config = generate_ui_config(df_head, table_name=table_name)
    path = Path(output_path) if output_path else BASE_DIR / "ui_config.json"
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path.resolve())


if __name__ == "__main__":
    # Quick smoke test with dummy data (50 rows)
    n = 50
    dummy = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "branch": (["A", "B", "C"] * 20)[:n],
        "product_category": (["Electronics", "Food", "Clothing"] * 20)[:n],
        "total_usd": ([100, 200, 150, 300, 250] * 10)[:n],
        "payment_method": (["Cash", "Card", "Transfer"] * 20)[:n],
        "shift": (["Morning", "Afternoon"] * 25)[:n],
        "cashier": (["Alice", "Bob", "Charlie"] * 20)[:n],
    })
    cfg = generate_ui_config(dummy, table_name="demo_data")
    out = BASE_DIR / "ui_config_test.json"
    out.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Config written to {out}")
    print(out.read_text(encoding="utf-8"))
