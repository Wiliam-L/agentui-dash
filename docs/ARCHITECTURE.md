# Arquitectura

## Resumen

AgentUI Dash sigue el patrón **Dumb Skeleton**: la UI y la capa de datos son ignorantes de los nombres de columna. Toda la inteligencia vive en `core/inference.py`, y todo el estado se describe en un solo archivo — `ui_config.json` — escrito por el servidor MCP.

```
Usuario  →  Agente IA  →  MCP Server  →  ui_config.json  →  Streamlit UI  →  DuckDB
```

## Flujo de trabajo

1. **Usuario** proporciona un archivo de datos (CSV o Excel) al agente de IA.
2. **Agente** llama a `create_dashboard()`, que encadena: ingesta → detección de columnas → KPIs → gráficos → filtros → guardar config.
3. **MCP Server** detecta los roles de columna, genera SQL y escribe de forma atómica `ui_config.json`.
4. **ui_config.json** es el contrato: módulos, filtros globales, KPIs con SQL, especificaciones de gráficos y mapeo de columnas.
5. **Streamlit UI** observa el timestamp de modificación del JSON y se auto-refresca cuando cambia (sin reiniciar el servidor).
6. **DuckDB** ejecuta las consultas con conexiones efímeras de solo lectura.

## Componentes

| Componente | Rol | Tecnología |
|---|---|---|
| `app_base/streamlit_ui/` | UI reactiva que renderiza `ui_config.json` | Streamlit, Plotly, CSS |
| `app_base/core/data.py` | Capa de datos: ingesta y ejecución SQL | DuckDB, pandas |
| `app_base/core/tools.py` | Puente JSON ↔ DuckDB: valida, guarda, ejecuta | Python |
| `app_base/core/inference.py` | Inteligencia: mapea columnas físicas a roles lógicos | Python |
| `app_base/core/chart_builder.py` | Construcción de gráficos y estilo Plotly | Plotly |
| `app_base/ui_config.json` | Contrato completo del dashboard | JSON |
| `agentui_mcp/server.py` | Servidor MCP expuesto al agente de IA | FastMCP |
| `agentui_mcp/tools/` | Implementaciones de herramientas por categoría | Python |

## Separación de Responsabilidades

- **El MCP escribe** `ui_config.json`.
- **La UI lee** `ui_config.json` y no sabe nada de lógica de negocio.
- **`core/tools.py`** traduce el config a consultas y valida el JSON.
- **`core/data.py`** solo ejecuta SQL; nunca adivina columnas ni tipos.
- **`core/inference.py`** concentra sinónimos y heurísticas de detección.

La ventaja es directa: el mismo sistema sirve ventas, inventario, logística o cualquier otro dominio cambiando solo los datos de entrada.

## Estructura del Repositorio

```
.
├── pyproject.toml              # Raíz del proyecto (uv sync / uv run ui)
├── .streamlit/config.toml      # Tema claro
├── Dockerfile                  # Imagen Docker
├── docker-compose.yml          # Servicios UI y MCP
├── app_base/
│   ├── __init__.py             # Paquete Python
│   ├── .streamlit/config.toml  # Tema claro (app)
│   ├── core/                   # data.py · tools.py · inference.py · chart_builder.py
│   ├── streamlit_ui/           # main.py · views/ · styles/
│   └── ui_config.json          # Contrato del dashboard
├── agentui_mcp/
│   ├── __init__.py             # Paquete Python
│   ├── __main__.py             # Permite `python -m agentui_mcp`
│   ├── server.py               # Servidor MCP (punto de entrada)
│   ├── instructions.py         # Instrucciones del agente
│   ├── utils.py                # Helpers compartidos
│   └── tools/                  # Herramientas por categoría
├── docs/
│   ├── TOOLS.md                # Referencia de herramientas MCP
│   ├── INSTALL.md              # Guía de instalación
│   └── ARCHITECTURE.md         # Este archivo
├── examples/                   # Datos de ejemplo para pruebas
└── build_mcp/                  # Wheel pre-construido y scripts de build
```

## Seguridad

- **Consultas de solo lectura** — la UI abre DuckDB en modo `read_only`.
- **Allow-list de SQL** — `safe_sql()` usa `sqlglot` para parsear el AST y bloquear operaciones de escritura, acceso a archivos o red.
- **Validación cruzada** — `cross_validate_config()` verifica que los totales de KPIs coincidan con las sumas de gráficos, detecta nulos y comprueba referencias de columnas.
- **Escritura atómica del JSON** — el MCP escribe en un archivo temporal y reemplaza con `os.replace`; la UI nunca lee un JSON a medio escribir.
- **Último config válido** — si el JSON es momentáneamente ilegible, el último config bueno se mantiene en el estado de sesión.
- **Conexiones efímeras** — las conexiones se abren y cierran por consulta para evitar bloqueo de archivos entre MCP y Streamlit en Windows.
