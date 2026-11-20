# 📊 Dashboard Automático — Guía para el Cliente

## ¿Qué es esto?

Es un sistema que convierte **cualquier archivo CSV/Excel en un dashboard interactivo automáticamente**. No necesitas saber programar, ni SQL, ni configurar nada. Solo necesitas tus datos y un asistente de IA (como Claude, ChatGPT, Cursor, etc.) conectado al servidor MCP.

---

## 🚀 Cómo usarlo — Lo más simple posible

### Paso 1: Abre tu asistente de IA

Abre tu herramienta de IA favorita (Claude, ChatGPT, Cursor, etc.) que tenga conectado el servidor MCP "Retail Analytics Dashboard".

### Paso 2: Dile qué quieres

Escribe algo tan simple como:

> **"Tengo un archivo con mis ventas en `C:/MisDatos/ventas.csv`, créame un dashboard."**

O también:

> **"Quiero ver un dashboard de mis datos que están en `C:/reporte_mensual.xlsx`"**

> **"Create a dashboard from this file: `/path/to/my_data.csv`"**

### Paso 3: Listo

El asistente automáticamente:
1. ✅ Carga tu archivo
2. ✅ Detecta qué es cada columna (fechas, montos, categorías, etc.)
3. ✅ Crea gráficos, indicadores (KPIs) y filtros
4. ✅ Guarda la configuración

En **3 segundos** el dashboard Streamlit muestra todo automáticamente.

---

## 💬 Ejemplos de lo que puedes decir

### En español:

| Lo que escribes | Qué pasa |
|---|---|
| `"Tengo ventas.csv en C:/datos/ventas.csv, créame un dashboard"` | Crea dashboard completo |
| `"Quiero un dashboard de mis datos en reporte.xlsx"` | Crea dashboard completo |
| `"Carga C:/ventas_2024.csv y hazme un panel de ventas"` | Crea dashboard con título personalizado |
| `"Agrega un gráfico de pastel por categoría"` | Agrega gráfico al dashboard existente |
| `"¿Cuántas ventas tengo en total?"` | Ejecuta consulta y te responde |

### En inglés:

| What you type | What happens |
|---|---|
| `"I have sales.csv at C:/data/sales.csv, create a dashboard"` | Creates full dashboard |
| `"Create a dashboard from this report: /path/to/report.csv"` | Creates full dashboard |
| `"Load C:/sales_2024.csv and make a sales panel"` | Creates dashboard with custom title |
| `"Add a pie chart by category"` | Adds chart to existing dashboard |
| `"What's my total sales?"` | Runs query and answers you |

---

## 🎨 ¿Qué incluye el dashboard automático?

Cuando el sistema analiza tus datos, detecta automáticamente:

- **📈 Indicadores (KPIs)**: Totales, promedios, conteos
- **📊 Gráficos**: Barras, pasteles, líneas (según tus datos)
- **🔍 Filtros**: Para filtrar por sucursal, categoría, fecha, etc.
- **📋 Tablas**: Datos detallados con scroll

Todo se adapta a **tus columnas**, sin importar cómo se llamen.

---

## ⚙️ Configuración técnica (para el administrador)

### Conectar el MCP Server

En tu cliente de IA, configura el servidor MCP así:

```
Command: python
Args: ["server.py"]
Working directory: C:\Users\wlope\Desktop\MCP_HACKATHON - copia\agentui-mcp
```

### Iniciar el Dashboard Streamlit

```bash
cd "C:\Users\wlope\Desktop\MCP_HACKATHON - copia\app_base"
streamlit run streamlit_ui/main.py
```

El dashboard se actualiza automáticamente cada 3 segundos cuando el MCP modifica la configuración.

### Archivos clave

| Archivo | Propósito |
|---|---|
| `ui_config.json` | Configuración del dashboard (generado automáticamente) |
| `agentui-mcp/server.py` | Servidor MCP con todas las herramientas |
| `streamlit_ui/main.py` | Aplicación Streamlit |
| `core/data.py` | Base de datos DuckDB |
| `core/inference.py` | Detección inteligente de columnas |

---

## 🧰 Herramientas disponibles en el MCP

El servidor MCP expone **21 herramientas** que el asistente de IA puede usar:

| Herramienta | Descripción |
|---|---|
| **`create_dashboard`** ⭐ | **Crea un dashboard completo en 1 paso** |
| `upload_csv` | Sube un archivo CSV |
| `detect_columns` | Detecta qué es cada columna |
| `generate_config` | Genera la configuración completa |
| `run_query` | Ejecuta una consulta SQL |
| `get_config` | Muestra la configuración actual |
| `update_config` | Actualiza la configuración |
| `preview_table` | Previsualiza datos |
| `list_tables` | Lista tablas cargadas |
| `clear_data` | Limpia todos los datos |
| ... y más | Gráficos, KPIs, filtros personalizados |

**La herramienta estrella es `create_dashboard()`**: hace todo en un solo paso.

---

## ❓ Preguntas frecuentes

**¿Qué formatos de archivo soporta?**
CSV y Excel (.xlsx).

**¿Puedo tener múltiples dashboards?**
Sí, cada vez que cargues un archivo nuevo, se crea una nueva tabla y se actualiza el dashboard.

**¿Qué pasa si mis columnas tienen nombres raros?**
El sistema detecta automáticamente si una columna es fecha, monto, categoría, etc., sin importar el nombre.

**¿Cómo limpio todo y empiezo de nuevo?**
Dile al asistente: `"Limpia todos los datos"` y usará `clear_data()`.
