# AgentUI Dash

Dashboards corporativos generados por un agente de IA a través de **MCP** (Model Context Protocol).

El usuario final solo indica un archivo CSV o Excel y el agente se encarga del resto: carga los datos en DuckDB, detecta el rol de cada columna, genera los KPIs, los gráficos y los filtros, escribe la configuración del dashboard y levanta Streamlit.

---

## Qué automatiza

- **Detección de columnas** — identifica el rol de cada columna (fecha, monto, categoría, sucursal, cantidad, etc.) mediante un diccionario de sinónimos con más de 100 variantes.
- **Generación de KPIs** — crea indicadores (totales, promedios, conteos, márgenes) a partir de las columnas detectadas.
- **Creación de gráficos** — elige el tipo de gráfico adecuado según los datos disponibles.
- **Configuración de filtros** — genera filtros globales (`select`, `multiselect`, `date_range`) sobre las columnas categóricas y temporales.
- **Construcción de la UI** — renderiza la interfaz completa desde un JSON, sin código *hardcoded*.
- **Gestión del servidor** — arranca, detiene y consulta el estado del servidor Streamlit.

## Finalidad

Eliminar la barrera técnica entre los datos y su visualización: cualquier persona sin conocimientos de programación puede obtener un dashboard corporativo funcional describiendo su necesidad en lenguaje natural a un agente de IA.

---

## Arquitectura

AgentUI Dash sigue el patrón **Dumb Skeleton**: la interfaz y la capa de datos son ciegas a los nombres de columnas. Toda la inteligencia vive en `core/inference.py` y todo el estado se describe en un único archivo, `ui_config.json`, que escribe el servidor MCP.

```
Usuario  →  Agente IA  →  MCP Server  →  ui_config.json  →  Streamlit UI  →  DuckDB
```

1. **Usuario** indica un archivo de datos (CSV o Excel) al agente.
2. **Agente** llama `create_dashboard()`, que encadena: ingesta → detección de columnas → KPIs → gráficos → filtros → guardado de configuración.
3. **MCP Server** (28 herramientas) detecta los roles de cada columna, genera el SQL y escribe `ui_config.json` de forma atómica.
4. **ui_config.json** es el contrato: módulos, filtros globales, KPIs con SQL, especificaciones de gráficos y mapeo de columnas.
5. **Streamlit UI** vigila la fecha de modificación del JSON y se refresca sola cuando cambia (sin reiniciar el servidor).
6. **DuckDB** ejecuta las consultas con conexiones efímeras de solo lectura.

### Componentes

| Componente | Rol | Tecnología |
|---|---|---|
| `app_base/streamlit_ui/` | Interfaz reactiva que renderiza `ui_config.json` | Streamlit, Plotly, CSS |
| `app_base/core/data.py` | Capa de datos cruda: ingesta y ejecución SQL | DuckDB, pandas |
| `app_base/core/tools.py` | Puente JSON ↔ DuckDB: valida, guarda y ejecuta | Python |
| `app_base/core/inference.py` | Inteligencia: mapea columnas físicas a roles lógicos | Python |
| `app_base/core/chart_builder.py` | Construcción y estilos de gráficos Plotly | Plotly |
| `app_base/ui_config.json` | Contrato completo del dashboard | JSON |
| `agentui-mcp/server.py` | Servidor MCP expuesto al agente | FastMCP |

### Separación de responsabilidades

- **El MCP escribe** `ui_config.json`.
- **La UI lee** `ui_config.json` y no sabe nada del negocio.
- **`core/tools.py`** traduce configuración a consultas y valida el JSON.
- **`core/data.py`** solo ejecuta SQL; nunca adivina columnas ni tipos.
- **`core/inference.py`** concentra los sinónimos y la heurística de detección.

La ventaja es directa: el mismo sistema sirve para ventas, inventario, logística o cualquier otro dominio cambiando únicamente los datos de entrada.

---

## Instalación

Requisitos: **Python 3.10+** y [**uv**](https://astral.sh/uv) (`pip install uv`).

Recomendado, desde la raíz del repositorio (un solo entorno virtual):

```powershell
uv sync
```

Alternativa en Windows con los scripts incluidos (crea un entorno local en `app_base/`):

```powershell
cd app_base
.\CONFIG_SETUP.bat
```

## Ejecución

### Dashboard

```powershell
uv run ui
```

o, en Windows:

```powershell
app_base\START_SERVER.bat
```

La UI queda disponible en `http://localhost:8501`.

Por defecto el servidor escucha solo en `127.0.0.1` (en Windows + Python 3.14 el bind IPv6 por defecto de Streamlit falla de forma intermitente con `WinError 64`). Para exponerlo en la red local:

```powershell
$env:AGENTUI_HOST = "0.0.0.0"
$env:AGENTUI_PORT = "8501"
uv run ui
```

### Servidor MCP

```powershell
uv run python agentui-mcp/server.py
```

Transporte `stdio`, pensado para que lo arranque el cliente de IA.

### Conectar el agente

Claude Desktop (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "uv",
      "args": ["run", "python", "agentui-mcp/server.py"],
      "cwd": "C:\\ruta\\a\\agentui-dash"
    }
  }
}
```

En Cursor: `Ctrl+Shift+P` → *Cursor: Manage MCP Servers*.
En Windsurf: *Settings* → *MCP Servers*.

Una vez conectado, basta con decirle al agente:

> «Tengo `ventas.csv`, créame un dashboard.»

El agente llamará `create_dashboard()` y devolverá la URL del resultado.

---

## Docker

### Dashboard con Docker

```powershell
docker compose up -d ui
```

O directamente con `docker`:

```powershell
docker build -t agentui-dash .
docker run -p 8501:8501 agentui-dash
```

La UI quedará en `http://localhost:8501`.

### Servidor MCP con Docker

Para conectar un cliente MCP (Claude Desktop, Cursor, Windsurf) al servidor que corre dentro del contenedor:

**Opción 1: docker compose (recomendado)**

```powershell
docker compose run --rm mcp
```

Esto arranca el servidor MCP en modo interactivo (stdin/stdout) listo para ser consumido por el cliente.

**Opción 2: docker run**

```powershell
docker run -i --rm agentui-dash python -m agentui_mcp.server
```

**Configuración del cliente**

En `claude_desktop_config.json` (o equivalente) usar el comando `docker` con los argumentos apropiados:

```json
{
  "mcpServers": {
    "agentui-docker": {
      "command": "docker",
      "args": [
        "exec", 
        "-i", 
        "mcp_hackathon-copia-mcp-1", 
        "python", 
        "-m", 
        "agentui_mcp.server"
      ]
    }
  }
}
```

Nota: el nombre del contenedor (`mcp_hackathon-copia-mcp-1`) depende del proyecto de Docker Compose. Se puede obtener con `docker ps`.

---

## El contrato `ui_config.json`

Todo lo que se ve en pantalla sale de este archivo. Un módulo mínimo se ve así:

```json
{
  "titulo_pagina": "Ventas | Corporate Analytics",
  "brand_name": "VENTAS",
  "brand_sub": "Corporate Analytics",
  "column_mapping": { "date": "Order Date", "sales": "Sales" },
  "filtros_globales": [
    { "nombre": "region", "etiqueta": "Región", "columna": "Region",
      "tabla": "ventas", "tipo": "multiselect", "todos_label": "Todas las regiones" }
  ],
  "modulos": [
    {
      "id": "resumen",
      "nombre": "Resumen Ejecutivo",
      "kpis": [
        { "label": "Ventas", "icono": "payments", "formato": "money",
          "sql": "SELECT SUM(Sales) AS v FROM ventas" }
      ],
      "graficos": [
        { "titulo": "Ventas por mes", "tipo": "line", "x": "Date", "y": "Total",
          "sql": "SELECT Order Date AS Date, SUM(Sales) AS Total FROM ventas GROUP BY 1" }
      ]
    }
  ]
}
```

Los filtros globales se inyectan automáticamente como cláusula `WHERE` en todas las consultas del módulo.

## Herramientas del MCP (28)

| Categoría | Herramientas |
|---|---|
| Dashboard | `create_dashboard` |
| Datos | `upload_csv`, `upload_multiple_csvs`, `preview_table`, `list_tables`, `get_table_columns`, `explore_data`, `clear_data` |
| Configuración | `generate_config`, `get_config`, `update_config` |
| Consultas | `run_query`, `run_query_with_filters`, `get_kpi` |
| Filtros | `get_filter_options`, `get_date_range` |
| Detección | `detect_columns`, `get_available_roles` |
| Gráficos | `list_chart_types`, `recommend_chart`, `build_chart_config`, `build_kpi_config`, `build_filter_config`, `build_module_config` |
| Servidor | `start_streamlit`, `stop_streamlit`, `check_streamlit_status` |

## Gráficos soportados

`bar`, `bar_h`, `bar_grouped`, `bar_stacked`, `line`, `pie`, `scatter`, `heatmap`

Formatos de KPI: `money`, `int`, `percent`, `str`.

---

## Recarga en caliente

La UI mantiene un fragmento ligero que comprueba cada 2 segundos la fecha de modificación de `ui_config.json`:

- Si el JSON **no cambió**, no ocurre nada (no se re-ejecutan consultas).
- Si el JSON **cambió**, la app se vuelve a ejecutar y muestra el dashboard nuevo.

Por eso el agente puede añadir un KPI o cambiar un gráfico en mitad de una sesión sin reiniciar Streamlit.

## Decisiones de robustez

- **Consultas de solo lectura** — la UI abre DuckDB en modo `read_only`; una consulta del dashboard no puede modificar la base de datos.
- **Escritura atómica del JSON** — el MCP escribe en un archivo temporal y lo reemplaza con `os.replace`, así la UI nunca lee un JSON a medio escribir.
- **Última configuración válida** — si el JSON está momentáneamente ilegible (o lleva BOM), se conserva la última configuración buena de la sesión en lugar de caer al dashboard vacío.
- **Errores visibles** — un SQL que falla ya no se traga en silencio: se registra en `app_base/log_trace_upload_data.log` y la UI muestra un desplegable con el mensaje real de DuckDB.
- **Conexiones efímeras** — se abren y cierran por consulta para evitar el bloqueo del archivo entre el proceso del MCP y el de Streamlit en Windows, y la conexión de escritura se libera al terminar cada ingesta.
- **Tema claro fijado** — el tema se define en `.streamlit/config.toml` y en el entrypoint (`--theme.*`), para que los widgets de BaseWeb no hereden el modo oscuro del sistema (el conocido bug de los campos negros).

## Estructura del repositorio

```
.
├── pyproject.toml              # Proyecto raíz (uv sync / uv run ui)
├── .streamlit/config.toml      # Tema claro (obligatorio, no ignorar)
├── app_base/
│   ├── core/                   # data.py · tools.py · inference.py · chart_builder.py
│   ├── streamlit_ui/           # main.py · views/ · styles/
│   ├── ui_config.json          # Contrato del dashboard
│   ├── assets/fonts/           # Iconos Material
│   ├── CONFIG_SETUP.bat        # Setup alternativo (Windows)
│   ├── START_SERVER.bat        # Arranque alternativo (Windows)
│   └── README_CLIENTE.md       # Guía para el usuario final
└── agentui-mcp/
    └── server.py               # Servidor MCP (28 herramientas)
```

---

## Estado y limitaciones conocidas

- El SQL de los KPIs y gráficos viene del JSON, así que la seguridad depende de lo que genere el agente. Está pendiente añadir un *allow-list* (por ejemplo con `sqlglot`, solo `SELECT`).
- No hay tests automatizados todavía; `core/inference.py` es el módulo que más los necesita.
- DuckDB admite un escritor o varios lectores, no ambos a la vez: el diseño usa conexiones efímeras para convivir, pero no es un motor multiusuario.
- Conviven dos `pyproject.toml` (raíz y `app_base/`) por compatibilidad con los scripts `.bat`; la unificación está en el roadmap.

## Roadmap

1. Tests de inferencia (`CSV de ejemplo → roles esperados`) y de contrato (`ui_config.json` válido).
2. *Allow-list* de SQL + validación estricta de columnas.
3. Un único `pyproject.toml` y un único entorno virtual.
4. Exportación a PDF y workspaces múltiples.

---

## Licencia

Modelo dual:

| Versión | Licencia | Uso |
|---|---|---|
| Open Source | [MIT](LICENSE) | Código base. Cualquiera puede usarlo, modificarlo y contribuir. |
| Comercial | [Licencia Comercial](LICENSE-COMMERCIAL.md) | Para clientes que compran el producto. Pueden usarlo, pero no revenderlo ni redistribuirlo. |

Para adquirir una licencia comercial: contacto@agentui-dash.com

---

> Rama de desarrollo: `develop`. `main` queda reservada para versiones estables.
