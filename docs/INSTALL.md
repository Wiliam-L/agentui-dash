# Guía de Instalación

## Requisitos previos

**uv** — un instalador de paquetes Python rápido. `uv` descarga e instala automáticamente Python 3.11+ si no lo tienes.

### Instalar uv

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Opción A: Paquete pre-construido (Recomendada)

Descarga el archivo `.whl` desde `build_mcp/` e instálalo globalmente:

```powershell
uv tool install agentui_dash-0.1.0-py3-none-any.whl
```

Después de la instalación, dos comandos están disponibles globalmente:

| Comando | Descripción |
|---|---|
| `ui` | Iniciar el dashboard Streamlit |
| `agentui-mcp` | Iniciar el servidor MCP para agentes de IA |

---

## Opción B: Desde el código fuente

Clona el repositorio e instala desde el directorio raíz:

```powershell
git clone https://github.com/Wiliam-L/agentui-dash.git
cd agentui-dash
uv sync
```

Ejecutar con:
```powershell
uv run ui          # Iniciar dashboard
uv run agentui-mcp # Iniciar servidor MCP
```

---

## Opción C: Docker

Para un entorno completamente aislado sin instalar Python ni `uv`:

```powershell
docker compose up --build
```

El dashboard estará disponible en `http://localhost:8501`.

---

## Conectar un Agente de IA

### Opencode

Si instalaste con `uv tool install`:

```powershell
opencode mcp add agentui-dash --global -- agentui-mcp
opencode mcp list
```

### Claude Desktop

Edita `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "uv",
      "args": ["run", "agentui-mcp"],
      "cwd": "C:\\path\\to\\agentui-dash"
    }
  }
}
```

### Cursor

`Ctrl+Shift+P` → *Cursor: Manage MCP Servers* → Agregar `agentui-mcp`.

### Windsurf

*Settings* → *MCP Servers* → Agregar `agentui-mcp`.

### Docker (Servidor MCP)

**Opción 1: docker compose (recomendada)**
```powershell
docker compose run --rm mcp
```

**Opción 2: docker run**
```powershell
docker run -i --rm agentui-dash python -m agentui_mcp.server
```

---

## Solución de problemas

### WinError 64 en Windows + Python 3.14

El enlace IPv6 por defecto de Streamlit puede fallar intermitentemente. Para solucionarlo, enlaza a IPv4:

```powershell
$env:AGENTUI_HOST = "0.0.0.0"
$env:AGENTUI_PORT = "8501"
uv run ui
```

### Servidor MCP No Encontrado

Si `agentui-mcp` no está en tu PATH después de `uv tool install`, usa:

```powershell
opencode mcp add agentui-dash --global -- python -m agentui_mcp
```
