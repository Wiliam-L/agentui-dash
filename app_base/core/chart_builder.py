"""Chart builder — helps the MCP agent choose and build chart configurations.

This module provides utilities so the MCP agent knows:
1. What chart types are available and when to use each one.
2. How to build a chart config dict for `render_chart()`.
3. How to recommend a chart type based on data characteristics.

The agent uses this to generate proper `ui_config.json` entries for charts.
No hardcoded column names — everything is driven by data analysis.
"""
from __future__ import annotations

import pandas as pd


# --------------------------------------------------------------------------- #
# Chart type registry — the single source of truth for available chart types
# --------------------------------------------------------------------------- #

CHART_TYPES = {
    "bar": {
        "description": "Vertical bar chart. Best for comparing values across categories.",
        "use_when": [
            "Comparing sales by branch, product, or region.",
            "Showing counts or totals grouped by a categorical axis.",
            "Displaying top-N rankings.",
        ],
        "required_keys": ["x", "y"],
        "optional_keys": ["color", "alto"],
        "example": {
            "tipo": "bar",
            "x": "Category",
            "y": "Sales",
            "alto": 380,
        },
    },
    "bar_h": {
        "description": "Horizontal bar chart. Best when category labels are long.",
        "use_when": [
            "Category names are long and would overlap on a vertical bar.",
            "Ranking items where the label is the focus.",
        ],
        "required_keys": ["x", "y"],
        "optional_keys": ["color", "alto"],
        "example": {
            "tipo": "bar_h",
            "x": "Sales",
            "y": "Product Name (Long Label)",
            "alto": 350,
        },
    },
    "pie": {
        "description": "Donut/pie chart. Best for showing parts of a whole (share/percentage).",
        "use_when": [
            "Showing market share, category distribution, or percentage breakdown.",
            "When there are 2–8 categories (avoid for many categories).",
        ],
        "required_keys": ["columna", "valores"],
        "optional_keys": ["alto"],
        "example": {
            "tipo": "pie",
            "columna": "Category",
            "valores": "Sales",
            "alto": 350,
        },
    },
    "line": {
        "description": "Line chart. Best for trends over time or ordered sequences.",
        "use_when": [
            "Showing sales trend over months, weeks, or days.",
            "Comparing multiple series over time (use 'color' for grouping).",
        ],
        "required_keys": ["x", "y"],
        "optional_keys": ["color", "alto"],
        "example": {
            "tipo": "line",
            "x": "Month",
            "y": "Sales",
            "color": "Branch",
            "alto": 350,
        },
    },
    "scatter": {
        "description": "Scatter plot. Best for correlation between two numeric variables.",
        "use_when": [
            "Analyzing relationship between price and quantity.",
            "Finding outliers or clusters in numeric data.",
            "Comparing margin vs units sold.",
        ],
        "required_keys": ["x", "y"],
        "optional_keys": ["color", "size", "alto"],
        "example": {
            "tipo": "scatter",
            "x": "Units",
            "y": "Margin_pct",
            "color": "Category",
            "alto": 380,
        },
    },
    "heatmap": {
        "description": "Heatmap matrix. Best for cross-tabulation of two categories with a value.",
        "use_when": [
            "Sales by branch × product category.",
            "Performance matrix: rows vs columns with intensity.",
        ],
        "required_keys": ["x", "y", "valores"],
        "optional_keys": ["alto"],
        "example": {
            "tipo": "heatmap",
            "x": "Branch",
            "y": "Category",
            "valores": "Sales",
            "alto": 400,
        },
    },
    "bar_grouped": {
        "description": "Grouped bar chart. Best for comparing sub-categories side by side.",
        "use_when": [
            "Sales by branch, grouped by product category.",
            "Comparing multiple metrics per category.",
        ],
        "required_keys": ["x", "y", "color"],
        "optional_keys": ["alto"],
        "example": {
            "tipo": "bar_grouped",
            "x": "Branch",
            "y": "Sales",
            "color": "Category",
            "alto": 380,
        },
    },
    "bar_stacked": {
        "description": "Stacked bar chart. Best for showing composition within each group.",
        "use_when": [
            "Total sales by branch, stacked by product category.",
            "Showing how each group breaks down into sub-parts.",
        ],
        "required_keys": ["x", "y", "color"],
        "optional_keys": ["alto"],
        "example": {
            "tipo": "bar_stacked",
            "x": "Branch",
            "y": "Sales",
            "color": "Category",
            "alto": 380,
        },
    },
}


# --------------------------------------------------------------------------- #
# Recommendation engine — suggests chart type based on DataFrame analysis
# --------------------------------------------------------------------------- #

def recomendar_grafica(df: pd.DataFrame, sql_context: str = "") -> list[dict]:
    """Recommend chart types based on DataFrame column analysis.

    Analyzes the DataFrame columns (types, cardinality, names) and suggests
    the most appropriate chart types with their config keys.

    Args:
        df: The DataFrame that will be used for the chart.
        sql_context: Optional SQL query string for additional context.

    Returns:
        List of recommended chart configs, each with:
        - tipo: chart type
        - razon: why this chart is recommended
        - config: partial config dict with suggested column mappings
    """
    if df.empty or len(df) == 0:
        return []

    recommendations = []
    cols = list(df.columns)
    n_cols = len(cols)

    # Classify columns
    categorical_cols = []
    numeric_cols = []
    date_cols = []

    for col in cols:
        dtype = df[col].dtype
        if pd.api.types.is_datetime64_any_dtype(dtype):
            date_cols.append(col)
        elif pd.api.types.is_numeric_dtype(dtype):
            # Check cardinality: if few unique values, treat as categorical
            unique_count = df[col].nunique()
            if unique_count <= 15 and unique_count < len(df) * 0.1:
                categorical_cols.append(col)
            else:
                numeric_cols.append(col)
        else:
            # Object/string type
            unique_count = df[col].nunique()
            if unique_count <= 20:
                categorical_cols.append(col)
            else:
                # High cardinality string — might be IDs, skip
                pass

    # Recommendation rules
    # Rule 1: 1 categorical + 1 numeric → bar chart
    if categorical_cols and numeric_cols:
        cat = categorical_cols[0]
        num = numeric_cols[0]
        recommendations.append({
            "tipo": "bar",
            "razon": f"Comparing {num} across {cat} categories ({df[cat].nunique()} groups).",
            "config": {"tipo": "bar", "x": cat, "y": num, "alto": 380},
        })

        # If many categories with long names, suggest horizontal bar
        if df[cat].nunique() > 5:
            recommendations.append({
                "tipo": "bar_h",
                "razon": f"Horizontal bar for {cat} with {df[cat].nunique()} categories (better for long labels).",
                "config": {"tipo": "bar_h", "x": num, "y": cat, "alto": 350},
            })

    # Rule 2: 1 categorical + 1 numeric → pie (if few categories)
    if categorical_cols and numeric_cols:
        cat = categorical_cols[0]
        num = numeric_cols[0]
        if df[cat].nunique() <= 8:
            recommendations.append({
                "tipo": "pie",
                "razon": f"Showing share of {num} by {cat} ({df[cat].nunique()} slices).",
                "config": {"tipo": "pie", "columna": cat, "valores": num, "alto": 350},
            })

    # Rule 3: 1 date + 1 numeric → line chart
    if date_cols and numeric_cols:
        recommendations.append({
            "tipo": "line",
            "razon": f"Trend of {numeric_cols[0]} over time ({date_cols[0]}).",
            "config": {"tipo": "line", "x": date_cols[0], "y": numeric_cols[0], "alto": 350},
        })

    # Rule 4: 2+ numeric → scatter
    if len(numeric_cols) >= 2:
        recommendations.append({
            "tipo": "scatter",
            "razon": f"Correlation between {numeric_cols[0]} and {numeric_cols[1]}.",
            "config": {"tipo": "scatter", "x": numeric_cols[0], "y": numeric_cols[1], "alto": 380},
        })

    # Rule 5: 2 categorical + 1 numeric → heatmap
    if len(categorical_cols) >= 2 and numeric_cols:
        recommendations.append({
            "tipo": "heatmap",
            "razon": f"Cross-tabulation of {categorical_cols[0]} × {categorical_cols[1]} with {numeric_cols[0]}.",
            "config": {
                "tipo": "heatmap",
                "x": categorical_cols[0],
                "y": categorical_cols[1],
                "valores": numeric_cols[0],
                "alto": 400,
            },
        })

    # Rule 6: 2 categorical + 1 numeric → bar_grouped
    if len(categorical_cols) >= 2 and numeric_cols:
        recommendations.append({
            "tipo": "bar_grouped",
            "razon": f"Grouped bars: {numeric_cols[0]} by {categorical_cols[0]}, grouped by {categorical_cols[1]}.",
            "config": {
                "tipo": "bar_grouped",
                "x": categorical_cols[0],
                "y": numeric_cols[0],
                "color": categorical_cols[1],
                "alto": 380,
            },
        })

    return recommendations


# --------------------------------------------------------------------------- #
# Config builder — creates complete chart config for ui_config.json
# --------------------------------------------------------------------------- #

def construir_config_grafico(
    tipo: str,
    sql: str,
    titulo: str,
    x: str = None,
    y: str = None,
    columna: str = None,
    valores: str = None,
    color: str = None,
    alto: int = 350,
    sub: str = "",
    icono: str = "insights",
) -> dict:
    """Build a complete chart config dict for ui_config.json.

    Args:
        tipo: Chart type (bar, pie, line, scatter, bar_h, heatmap, bar_grouped, bar_stacked).
        sql: SQL query to get the data for this chart.
        titulo: Chart title shown in the card header.
        x: X-axis column name (for bar, line, scatter, heatmap, bar_grouped, bar_stacked).
        y: Y-axis column name (for bar, bar_h, line, scatter, bar_grouped, bar_stacked).
        columna: Category column name (for pie charts, replaces 'x').
        valores: Value column name (for pie charts, replaces 'y').
        color: Color grouping column name.
        alto: Chart height in pixels.
        sub: Subtitle text.
        icono: Material icon name for the card header.

    Returns:
        Dict ready to be placed in ui_config.json['modulos'][N]['graficos'].
    """
    if tipo not in CHART_TYPES:
        raise ValueError(
            f"Unknown chart type: '{tipo}'. "
            f"Available: {', '.join(CHART_TYPES.keys())}"
        )

    config = {
        "tipo": tipo,
        "titulo": titulo,
        "sub": sub,
        "icono": icono,
        "sql": sql,
        "alto": alto,
    }

    # Add type-specific keys
    if tipo == "pie":
        if columna:
            config["columna"] = columna
        if valores:
            config["valores"] = valores
    elif tipo == "heatmap":
        if x:
            config["x"] = x
        if y:
            config["y"] = y
        if valores:
            config["valores"] = valores
    else:
        # bar, bar_h, line, scatter, bar_grouped, bar_stacked
        if x:
            config["x"] = x
        if y:
            config["y"] = y
        if color:
            config["color"] = color

    return config


# --------------------------------------------------------------------------- #
# KPI config builder
# --------------------------------------------------------------------------- #

def construir_config_kpi(
    sql: str,
    label: str,
    icono: str,
    formato: str = "number",
    color: str = "#246bfd",
    sub_label: str = "",
    sub_sql: str = "",
    sub_prefix: str = "",
    sub_suffix: str = "",
    sub_format: str = "int",
) -> dict:
    """Build a complete KPI config dict for ui_config.json.

    Args:
        sql: SQL query that returns a single value.
        label: KPI label shown on the card.
        icono: Material icon name.
        formato: Value format ("money", "int", "percent", "str").
        color: Accent color hex.
        sub_label: Static sub-label text (alternative to sub_sql).
        sub_sql: SQL for dynamic sub-label.
        sub_prefix: Text before sub-value.
        sub_suffix: Text after sub-value.
        sub_format: Format for sub-value.

    Returns:
        Dict ready to be placed in ui_config.json['modulos'][N]['kpis'].
    """
    config = {
        "icono": icono,
        "label": label,
        "sql": sql,
        "formato": formato,
        "color": color,
    }
    if sub_label:
        config["sub_label"] = sub_label
    if sub_sql:
        config["sub_sql"] = sub_sql
        config["sub_prefix"] = sub_prefix
        config["sub_suffix"] = sub_suffix
        config["sub_format"] = sub_format
    return config


# --------------------------------------------------------------------------- #
# Filter config builder
# --------------------------------------------------------------------------- #

def construir_config_filtro(
    nombre: str,
    columna: str,
    tabla: str,
    tipo: str = "select",
    etiqueta: str = "",
    todos_label: str = "All",
) -> dict:
    """Build a filter config dict for ui_config.json.

    Args:
        nombre: Filter key name (used in filtros_valores dict).
        columna: Physical column name in DuckDB.
        tabla: Table name in DuckDB.
        tipo: Filter type ("select", "date_range", "multiselect").
        etiqueta: Display label in the sidebar.
        todos_label: Label for "All" option in select filters.

    Returns:
        Dict ready to be placed in ui_config.json['filtros_globales'].
    """
    config = {
        "nombre": nombre,
        "columna": columna,
        "tabla": tabla,
        "tipo": tipo,
    }
    if etiqueta:
        config["etiqueta"] = etiqueta
    if tipo == "select":
        config["todos_label"] = todos_label
    return config


# --------------------------------------------------------------------------- #
# Module config builder
# --------------------------------------------------------------------------- #

def construir_config_modulo(
    modulo_id: str,
    nombre: str,
    icono: str = "📋",
    material_icon: str = "dashboard",
    descripcion: str = "",
    breadcrumbs: str = "",
    kpis: list[dict] | None = None,
    graficos: list[dict] | None = None,
    tablas: list[dict] | None = None,
) -> dict:
    """Build a complete module config dict for ui_config.json.

    Args:
        modulo_id: Unique module identifier (e.g., "dashboard", "operations").
        nombre: Display name.
        icono: Emoji icon for sidebar navigation.
        material_icon: Material icon for page header.
        descripcion: Module description text.
        breadcrumbs: Breadcrumb navigation text.
        kpis: List of KPI config dicts.
        graficos: List of chart config dicts.
        tablas: List of table config dicts.

    Returns:
        Dict ready to be placed in ui_config.json['modulos'].
    """
    config = {
        "id": modulo_id,
        "nombre": nombre,
        "icono": icono,
        "descripcion": descripcion,
        "material_icon": material_icon,
        "breadcrumbs": breadcrumbs or f"HOME  /  {modulo_id.upper()}",
    }
    if kpis:
        config["kpis"] = kpis
    if graficos:
        config["graficos"] = graficos
    if tablas:
        config["tablas"] = tablas
    return config


# --------------------------------------------------------------------------- #
# Quick reference for the MCP agent
# --------------------------------------------------------------------------- #

def listar_tipos_grafica() -> str:
    """Return a human-readable list of all chart types with usage guidance.

    Useful for the MCP agent to understand what chart types are available.
    """
    lines = ["Available chart types:\n"]
    for tipo, info in CHART_TYPES.items():
        lines.append(f"\n  {tipo}:")
        lines.append(f"    {info['description']}")
        lines.append(f"    Required keys: {', '.join(info['required_keys'])}")
        lines.append(f"    Optional keys: {', '.join(info['optional_keys'])}")
        lines.append(f"    Use when:")
        for use in info["use_when"]:
            lines.append(f"      - {use}")
    return "\n".join(lines)
