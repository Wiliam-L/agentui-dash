@echo off
REM ---------------------------------------------------------------------------
REM Configuracion inicial de AgentUI Base (Windows)
REM Usa uv para crear el entorno virtual e instalar las dependencias
REM desde pyproject.toml. Ejecuta este script una sola vez.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PROJECT_DIR=%~dp0"

color 0A
cls

echo.
echo  =========================================================
echo    AGENTUI BASE - Configuracion
echo  =========================================================
echo.

REM Verificar que uv exista
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo  [ERROR] No se encontro 'uv' en el PATH.
    echo          Instala uv:  pip install uv
    echo          O desde el sitio:  https://astral.sh/uv
    echo.
    pause
    exit /b 1
)

REM Comprobar que existe pyproject.toml
if not exist "%PROJECT_DIR%\pyproject.toml" (
    echo  [ERROR] No se encontro pyproject.toml en:
    echo          %PROJECT_DIR%
    echo          Verifica la estructura del proyecto.
    echo.
    pause
    exit /b 1
)

REM --- Instalar dependencias con uv -----------------------------------------
echo  [..] Instalando dependencias desde pyproject.toml ...
uv venv
if %errorlevel% neq 0 (
    echo  [ERROR] Fallo al crear el entorno virtual.
    echo.
    pause
    exit /b 1
)

uv pip install -e ".[mcp]"
if %errorlevel% neq 0 (
    echo  [ERROR] Fallo la instalacion de dependencias.
    echo          Revisa la conexion a internet y reintenta.
    echo.
    pause
    exit /b 1
)

echo.
echo  =========================================================
echo    Configuracion completada correctamente.
echo    Ahora ejecuta START_SERVER.bat para iniciar el dashboard.
echo  =========================================================
echo.
pause
endlocal
