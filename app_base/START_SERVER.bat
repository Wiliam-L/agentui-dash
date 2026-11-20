@echo off
REM ---------------------------------------------------------------------------
REM Arranque del dashboard AgentUI Base (Windows)
REM Usa uv run para lanzar Streamlit sin activar manualmente el venv.
REM Muestra una pantalla limpia con las URLs y oculta los logs de Streamlit
REM (se guardan en streamlit.log). Cerrar esta ventana detiene el servidor.
REM ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PROJECT_DIR=%~dp0"
set "PORT=8501"
set "LOG=%PROJECT_DIR%\streamlit.log"

color 0A
cls

echo.
echo  =========================================================
echo    AGENTUI BASE - Dashboard
echo  =========================================================
echo.

REM Verificar que uv exista
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo  [ERROR] No se encontro 'uv' en el PATH.
    echo          Ejecuta primero CONFIG_SETUP.bat o instala uv.
    echo.
    pause
    exit /b 1
)

REM Verificar que exista el entorno virtual
if not exist "%PROJECT_DIR%\.venv" (
    echo  [ERROR] No se encontro el entorno virtual.
    echo          Ejecuta primero CONFIG_SETUP.bat.
    echo.
    pause
    exit /b 1
)

REM --- Enviar al directorio del proyecto ------------------------------------
cd /d "%PROJECT_DIR%"

REM --- Comprobar si el puerto ya esta ocupado -------------------------------
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>nul
if %errorlevel% equ 0 (
    echo  [AVISO] El puerto %PORT% ya esta en uso.
    echo          Parece que el dashboard ya esta corriendo.
    echo.
    echo  Abre el navegador en:  http://localhost:%PORT%
    echo.
    echo  Para detenerlo, cierra la ventana correspondiente.
    echo.
    pause
    exit /b 0
)

REM --- Obtener la IP local de red (para compartir) --------------------------
set "IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /R /C:"IPv4"') do (
    set "IP=%%a"
    goto :_got_ip
)
:_got_ip
set "IP=%IP: =%"

cls
echo.
echo  =========================================================
echo    AGENTUI BASE - Dashboard
echo  =========================================================
echo.
echo  El servidor esta en linea.
echo.
echo  Abre el dashboard en tu navegador:
echo      Local:  http://localhost:%PORT%
if defined IP (
    echo  Red:   http://%IP%:%PORT%   ^(para compartir en tu red^)
)
echo.
echo  #  IMPORTANTE: cerrar ESTA ventana detiene el servidor. #
echo.
echo  Los detalles tecnicos se guardan en: %LOG%
echo  =========================================================
echo.

REM --- Lanzar Streamlit con uv run (output a log para pantalla limpia)
uv run streamlit run streamlit_ui\main.py --server.address 127.0.0.1 --server.port %PORT% --server.headless true >"%LOG%" 2>&1

echo.
echo  =========================================================
echo    El servidor se ha detenido.
echo    Gracias por usar AgentUI.
echo  =========================================================
echo.
pause
endlocal
