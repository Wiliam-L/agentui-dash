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
3. **MCP Server** detecta los roles de cada columna, genera el SQL y escribe `ui_config.json` de forma atómica.
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
| `agentui_mcp/server.py` | Servidor MCP expuesto al agente | FastMCP |

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

Desde la raíz del repositorio:

```powershell
uv sync
```

## Ejecución

### Dashboard

```powershell
uv run ui
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
uv run agentui-mcp
```

Transporte `stdio`, pensado para que lo arranque el cliente de IA.

### Conectar el agente

Claude Desktop (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "uv",
      "args": ["run", "agentui-mcp"],
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

### Dashboard

```powershell
docker compose up -d ui
```

O directamente con `docker`:

```powershell
docker build -t agentui-dash .
docker run -p 8501:8501 agentui-dash
```

La UI quedará en `http://localhost:8501`.

### Servidor MCP

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
        "<nombre-del-contenedor>",
        "python",
        "-m",
        "agentui_mcp.server"
      ]
    }
  }
}
```

Nota: el nombre del contenedor depende del proyecto de Docker Compose. Obténlo con `docker ps`.

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

## Herramientas del MCP

| Categoría | Herramientas |
|---|---|
| Dashboard | `create_dashboard` |
| Datos | `upload_csv`, `upload_multiple_csvs`, `update_data`, `analyze_relationships`, `preview_table`, `list_tables`, `get_table_columns`, `explore_data`, `clear_data` |
| Configuración | `generate_config`, `get_config`, `load_config`, `update_config`, `validate_config`, `cross_validate_config` |
| Consultas | `run_query`, `run_query_with_filters`, `get_kpi` |
| Filtros | `get_filter_options`, `get_date_range` |
| Detección | `detect_columns`, `get_available_roles` |
| Gráficos | `list_chart_types`, `recommend_chart`, `build_chart_config`, `build_kpi_config`, `build_filter_config`, `build_module_config` |
| Servidor | `start_streamlit`, `stop_streamlit`, `check_streamlit_status` |

Todas las herramientas son públicas y accesibles por el agente de IA. El motor valida todo el SQL generado mediante `safe_sql()` (con `sqlglot`), la estructura JSON mediante `validate_config()`, y la consistencia de cálculos mediante `cross_validate_config()`, por lo que el agente puede construir dashboards confiables sin riesgo.

## Gráficos soportados

`bar`, `bar_h`, `bar_grouped`, `bar_stacked`, `line`, `pie`, `scatter`, `heatmap`

Formatos de KPI: `money`, `int`, `percent`, `str`.

---

## Recarga en caliente

La UI mantiene un fragmento ligero que comprueba cada 2 segundos la fecha de modificación de `ui_config.json`:

- Si el JSON **no cambió**, no ocurre nada (no se re-ejecutan consultas).
- Si el JSON **cambió**, la app se vuelve a ejecutar y muestra el dashboard nuevo.

Por eso el agente puede añadir un KPI o cambiar un gráfico en mitad de una sesión sin reiniciar Streamlit.

## Actualización de datos

El dashboard incluye un **file uploader** en la barra lateral que permite al usuario final actualizar los datos sin depender del agente de IA. La función solo está disponible cuando ya existe un dashboard generado y valida que las columnas del archivo subido coincidan con las esperadas según `ui_config.json`. Si faltan columnas, se rechaza el archivo; si hay columnas adicionales, se acepta con una advertencia.

## Seguridad y robustez

- **Consultas de solo lectura** — la UI abre DuckDB en modo `read_only`; una consulta del dashboard no puede modificar la base de datos.
- **Validación SQL con allow-list** — `safe_sql()` usa `sqlglot` para parsear el AST y bloquear operaciones de escritura, acceso a archivos o red antes de ejecutar cualquier consulta.
- **Validación cruzada de cálculos** — `cross_validate_config()` verifica que los totales de los KPIs coincidan con la suma de las barras de los gráficos, detecta valores nulos, comprueba que las columnas referenciadas existen en los resultados SQL, y alerta sobre patrones sospechosos (valores idénticos, ceros inesperados).
- **Escritura atómica del JSON** — el MCP escribe en un archivo temporal y lo reemplaza con `os.replace`, así la UI nunca lee un JSON a medio escribir.
- **Última configuración válida** — si el JSON está momentáneamente ilegible (o lleva BOM), se conserva la última configuración buena de la sesión en lugar de caer al dashboard vacío.
- **Errores visibles** — un SQL que falla se registra en el log y la UI muestra un desplegable con el mensaje real de DuckDB.
- **Conexiones efímeras** — se abren y cierran por consulta para evitar el bloqueo del archivo entre el proceso del MCP y el de Streamlit en Windows, y la conexión de escritura se libera al terminar cada ingesta.
- **Tema claro fijado** — el tema se define en `.streamlit/config.toml` y en el entrypoint (`--theme.*`), para que los widgets de BaseWeb no hereden el modo oscuro del sistema.

## Estructura del repositorio

```
.
├── pyproject.toml              # Proyecto raíz (uv sync / uv run ui)
├── .streamlit/config.toml      # Tema claro
├── Dockerfile                  # Imagen Docker
├── docker-compose.yml          # Servicios UI y MCP
├── app_base/
│   ├── .streamlit/config.toml  # Tema claro (app)
│   ├── core/                   # data.py · tools.py · inference.py · chart_builder.py
│   ├── streamlit_ui/           # main.py · views/ · styles/
│   └── ui_config.json          # Contrato del dashboard
├── agentui_mcp/
│   ├── server.py               # Servidor MCP (entry point)
│   ├── instructions.py         # Instrucciones del agente
│   ├── utils.py                # Helpers compartidos
│   └── tools/                  # Herramientas por categoría
└── tests/
    ├── test_inference.py       # Tests de inferencia y seguridad SQL
    ├── test_mcp_tools.py       # Tests de herramientas MCP
    └── fixtures/               # Datos de prueba
```

---

## Limitaciones conocidas

- DuckDB admite un escritor o varios lectores, no ambos a la vez: el diseño usa conexiones efímeras para convivir, pero no es un motor multiusuario.
- El SQL de los KPIs y gráficos viene del JSON generado por el agente; la validación `safe_sql()` mitiga riesgos, pero la calidad depende de lo que el agente produzca.
- El dashboard está diseñado para **archivos de datos relacionados** (mismo dominio, misma estructura de columnas). Si se cargan archivos no relacionados, el agente debe usar `analyze_relationships()` para decidir cuáles incluir y generar dashboards separados cuando corresponda.
- No hay soporte automático para JOINs entre tablas; el agente puede escribir consultas con JOINs manualmente mediante `update_config()`.

## Roadmap

1. Exportación a PDF y workspaces múltiples.
2. Soporte para fuentes de datos externas (PostgreSQL, MySQL).
3. Personalización avanzada de temas y layouts.

---

## Licencia

AgentUI Dash se distribuye bajo **licencia comercial**. Consulta el archivo
[LICENSE](LICENSE) para los términos legales completos.

En resumen:

- Puedes usar, modificar y adaptar el software para tu negocio.
- Puedes crear dashboards para tus clientes con el software.
- No puedes revender, sublicenciar o redistribuir el software como producto independiente.
- No transfieres la propiedad intelectual al autor original.

El autor conserva todos los derechos y puede vender licencias a múltiples compradores.
Cada licencia es independiente y perpetua.

Para adquirir una licencia o más detalles: [LICENSE-COMMERCIAL.md](LICENSE-COMMERCIAL.md)

---

> Rama de desarrollo: `develop`. `main` queda reservada para versiones estables.