# Build the AgentUI Dash wheel package.
# Usage: .\build_mcp\build.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir

Write-Host "=== Building AgentUI Dash ===" -ForegroundColor Cyan
Set-Location $Root

# Clean previous build
Remove-Item -Recurse -Force dist, build, *.egg-info -ErrorAction SilentlyContinue

# Build
uv build

# Show results
Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Green
Get-ChildItem dist\ | Format-Table Name, Length -AutoSize

$Wheel = Get-ChildItem dist\*.whl | Select-Object -First 1
Write-Host ""
Write-Host "To install:" -ForegroundColor Yellow
Write-Host "  uv pip install --system $($Wheel.FullName)"
Write-Host ""
Write-Host "After installation, run:" -ForegroundColor Yellow
Write-Host "  ui              # Start the Streamlit dashboard"
Write-Host "  agentui-mcp     # Start the MCP server"
