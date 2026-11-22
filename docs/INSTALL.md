# Guía de Instalación

## Requisitos previos

**uv** — un gestor de paquetes Python rápido. Cuando ejecutas un comando de `uv` que requiere Python, este se descarga automáticamente (Python 3.10+) si no lo tienes instalado.

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

## Opción A: Desde el código fuente (Recomendada)

Clona el repositorio e instala las dependencias:

```powershell
git clone https://github.com/Wiliam-L/agentui-dash.git
cd agentui-dash
uv sync
```

`uv sync` descarga Python automáticamente si no lo tienes, e instala todas las dependencias.

Ejecutar con:
```powershell
uv run ui          # Iniciar dashboard
uv run agentui-mcp # Iniciar servidor MCP
```

---

## Opción B: Docker

Para un entorno completamente aislado sin instalar Python ni `uv`:

```powershell
docker compose up --build
```

El dashboard estará disponible en `http://localhost:8501`.

---

## Conectar un Agente de IA

### Opencode

Agrega esta entrada en `~/.config/opencode/opencode.jsonc`:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "uv",
      "args": ["run", "agentui-mcp"]
    }
  }
}
```

### Junie

Agrega esta entrada en `~/.junie/mcp/mcp.json`:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "uv",
      "args": ["run", "agentui-mcp"]
    }
  }
}
```

> ⚠️ En ambos casos, asegúrate de que el comando se ejecute desde el directorio del repositorio clonado, o agrega un campo `cwd` con la ruta al proyecto.

### Claude Desktop

Edita `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "agentui-mcp"
    }
  }
}
```

Si `agentui-mcp` no se encuentra en el PATH, usa:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "python",
      "args": ["-m", "agentui_mcp"]
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

Si `uv run agentui-mcp` no funciona, usa el módulo directamente en la configuración JSON:

```json
{
  "mcpServers": {
    "agentui-dash": {
      "command": "python",
      "args": ["-m", "agentui_mcp"]
    }
  }
}
```

### Exportación a PDF no disponible

La exportación a PDF requiere `weasyprint`, que depende de bibliotecas del sistema (`pango`, `gdk-pixbuf`). Si ves un error de `ImportError` al exportar:

- **Con `uv sync`**: la dependencia se instala automáticamente con `uv sync`.
- **Docker**: las bibliotecas del sistema ya están incluidas en el `Dockerfile`.
- **Windows manual**: instala `weasyprint` con `pip install weasyprint`. Si falla, usa la imagen Docker.
