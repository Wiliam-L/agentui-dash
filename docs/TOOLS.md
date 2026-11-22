# Herramientas MCP

AgentUI Dash expone **29 herramientas MCP públicas** accesibles por cualquier agente de IA. Todo SQL se valida con `safe_sql()` (sqlglot), la estructura JSON con `validate_config()`, y la consistencia de cálculos con `cross_validate_config()`.

## Dashboard

| Herramienta | Descripción |
|---|---|
| `create_dashboard` | Creación integral: ingesta → detección → generación de config → inicio de UI |

## Datos

| Herramienta | Descripción |
|---|---|
| `upload_csv` | Cargar un archivo CSV/Excel; crea una tabla única por archivo |
| `upload_multiple_csvs` | Cargar múltiples archivos; cada uno obtiene su propia tabla |
| `update_data` | Actualizar una tabla existente con validación de columnas |
| `analyze_relationships` | Detectar relaciones entre tablas cargadas (mismo esquema, columnas comunes, sin relación) |
| `preview_table` | Previsualizar las primeras 10 filas de una tabla |
| `list_tables` | Listar todas las tablas disponibles |
| `get_table_columns` | Obtener nombres y tipos de columna de una tabla |
| `explore_data` | Explorar estadísticas de datos (conteos, nulos, tipos) |
| `clear_data` | Limpiar todos los datos y la configuración |

## Configuración

| Herramienta | Descripción |
|---|---|
| `generate_config` | Generar automáticamente `ui_config.json` desde las tablas cargadas |
| `get_config` | Leer el `ui_config.json` actual |
| `load_config` | Cargar configuración desde archivo |
| `update_config` | Actualizar campos específicos en `ui_config.json` |
| `validate_config` | Validar estructura del config y ejecutar consultas SQL |
| `cross_validate_config` | Validar cruzado: totales de KPIs coinciden con sumas de gráficos, detectar nulos, verificar referencias de columnas |

## Consultas

| Herramienta | Descripción |
|---|---|
| `run_query` | Ejecutar una consulta SQL de solo lectura |
| `run_query_with_filters` | Ejecutar SQL con filtros globales inyectados |
| `get_kpi` | Ejecutar una consulta KPI individual |

## Filtros

| Herramienta | Descripción |
|---|---|
| `get_filter_options` | Obtener valores distintos para una columna de filtro |
| `get_date_range` | Obtener fechas mínimas/máximas para una columna de fecha |

## Detección

| Herramienta | Descripción |
|---|---|
| `detect_columns` | Detectar roles de columna (sucursal, fecha, categoría, monto, etc.) |
| `get_available_roles` | Listar todos los roles de columna disponibles |

## Constructor de Gráficos

| Herramienta | Descripción |
|---|---|
| `list_chart_types` | Listar tipos de gráficos disponibles (barra, pastel, línea, dispersión, mapa de calor, etc.) |
| `recommend_chart` | Recomendar tipo de gráfico basado en una consulta SQL |
| `build_chart_config` | Construir configuración JSON de un gráfico |
| `build_kpi_config` | Construir configuración JSON de un KPI |
| `build_filter_config` | Construir configuración JSON de un filtro |
| `build_module_config` | Construir configuración JSON completa de un módulo |

## Servidor

| Herramienta | Descripción |
|---|---|
| `start_streamlit` | Iniciar el servidor del dashboard Streamlit |
| `stop_streamlit` | Detener el servidor Streamlit |
| `check_streamlit_status` | Verificar si Streamlit está en ejecución |

## Tipos de Gráficos Soportados

`bar`, `bar_h`, `bar_grouped`, `bar_stacked`, `line`, `pie`, `scatter`, `heatmap`

## Formatos de KPI

`money`, `int`, `percent`, `str`
