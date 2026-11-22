# AgentUI Dash

**Genera un dashboard corporativo desde un CSV en minutos con un agente de IA.**

AgentUI Dash conecta un agente de IA (vía MCP) con DuckDB y Streamlit para crear dashboards funcionales: el agente carga los datos, detecta columnas, genera KPIs y gráficos, y entrega un dashboard listo para usar. Los números se validan con verificación cruzada automática.

## Para quién es

Para **freelancers y agencias** que crean dashboards para clientes.

| Sin AgentUI Dash | Con AgentUI Dash |
|---|---|
| Horas de código SQL y Python | Minutos con un prompt |
| Riesgo de errores de cálculo | Validación cruzada automática |
| Dashboard único por proyecto | Reutilizable con cualquier CSV |

## Quickstart

**Paso 1 — Instalar uv** (descarga Python automáticamente)

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Paso 2 — Clonar el repositorio e instalar**

```powershell
git clone https://github.com/Wiliam-L/agentui-dash.git
cd agentui-dash
uv sync
```

`uv sync` instala Python automáticamente si no lo tienes, y descarga todas las dependencias necesarias.

**Paso 3 — Conectar con Opencode**

```powershell
opencode mcp add agentui-dash --global -- agentui-mcp
```

**Paso 4 — Probar con datos de ejemplo**

Un CSV de ejemplo ya viene incluido en [`examples/ventas.csv`](examples/ventas.csv). Dile al agente:

> «Tengo `examples/ventas.csv`, créame un dashboard.»

El agente llamará `create_dashboard()` y devolverá la URL del resultado.

## Cómo funciona

```
Usuario  →  Agente IA  →  MCP Server  →  ui_config.json  →  Streamlit UI  →  DuckDB
```

1. El usuario indica un archivo CSV o Excel al agente.
2. El agente ingesta los datos en DuckDB, detecta el rol de cada columna, y genera KPIs y gráficos.
3. El MCP escribe `ui_config.json` — el contrato completo del dashboard.
4. Streamlit lee el JSON y renderiza la UI. Si el JSON cambia, se actualiza en caliente sin reiniciar.

[Arquitectura detallada →](docs/ARCHITECTURE.md)

## Por qué puedes confiar en los números

- **`cross_validate_config()`** — verifica que los totales de los KPIs coincidan con la suma de las barras de los gráficos. Si no coinciden, alerta al agente para que corrija.
- **`safe_sql()`** — usa `sqlglot` para parsear el AST de cada consulta y bloquea operaciones de escritura, acceso a archivos o red antes de ejecutar.
- **`validate_config()`** — ejecuta cada consulta SQL del config y verifica que retorna resultados válidos.
- **Validación de columnas** — al actualizar datos, se comprueba que las columnas del nuevo archivo coincidan con las esperadas.

## Personalización y entrega al cliente

- **White-label** — cambia `brand_name`, `brand_sub`, `brand_icon` y `footer` en el config para personalizar la marca.
- **Actualización de datos** — el dashboard incluye un file uploader para que el cliente actualice los datos sin depender del agente.
- **Docker** — entrega el dashboard como contenedor aislado: `docker compose up --build`.
- **Recarga en caliente** — el agente puede modificar KPIs o gráficos en tiempo real sin reiniciar Streamlit.
- **JSON como contrato** — `ui_config.json` define la estructura del dashboard (módulos, KPIs, gráficos, filtros). Cualquier frontend que conozca este esquema puede consumirlo, no solo Streamlit.

## Herramientas MCP

El agente tiene acceso a **30 herramientas públicas** organizadas en categorías: dashboard, datos, configuración, consultas, filtros, detección, gráficos y servidor.

[Lista completa de herramientas →](docs/TOOLS.md)

**Tipos de gráficos:** `bar`, `bar_h`, `bar_grouped`, `bar_stacked`, `line`, `pie`, `scatter`, `heatmap`

## Instalación avanzada

Para todas las opciones de instalación (código fuente, Docker, otros clientes MCP, troubleshooting):

[Guía de instalación →](docs/INSTALL.md)

## Limitaciones conocidas

- DuckDB no es un motor multiusuario: el diseño usa conexiones efímeras para convivir entre MCP y Streamlit.
- El SQL de KPIs y gráficos viene del agente; `safe_sql()` mitiga riesgos, pero la calidad depende de lo que el agente produzca.
- El dashboard está diseñado para **archivos de datos relacionados** (mismo dominio). Para archivos no relacionados, el agente debe generar dashboards separados.
- No hay soporte automático para JOINs entre tablas; el agente puede escribirlos manualmente con `update_config()`.

## Roadmap

1. Workspaces múltiples (aislar dashboards por proyecto).
2. Exportación a PDF.
3. Fuentes de datos externas (PostgreSQL, MySQL).
4. Personalización avanzada de temas y layouts.

## Licencia

[MIT](LICENSE) — libre para evaluación y demo.