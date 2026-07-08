# Vibe-Trading local startup helper for Windows.
#
# Usage:
#   .\start-local.ps1              # backend + frontend (default)
#   .\start-local.ps1 both         # same as above
#   .\start-local.ps1 backend      # API only  -> http://127.0.0.1:8899
#   .\start-local.ps1 frontend     # Web UI only -> http://127.0.0.1:5899
#   .\start-local.ps1 setup        # first-time: venv, pip install, npm install
#   .\start-local.ps1 docker       # Docker Compose (backend on 8899)
#   .\start-local.ps1 chat         # interactive CLI chat (no web UI)
#
# Prerequisites:
#   - Python 3.11+ (3.12 recommended)
#   - Node.js 18+ (for frontend dev)
#   - agent/.env with at least one LLM provider key (see agent/.env.example)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentDir = Join-Path $Root "agent"
$FrontendDir = Join-Path $Root "frontend"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$VenvVibe = Join-Path $Root ".venv\Scripts\vibe-trading.exe"
$EnvFile = Join-Path $AgentDir ".env"
$EnvExample = Join-Path $AgentDir ".env.example"
$BackendPort = if ($env:VIBE_BACKEND_PORT) { $env:VIBE_BACKEND_PORT } else { "8899" }
$FrontendPort = if ($env:VIBE_FRONTEND_PORT) { $env:VIBE_FRONTEND_PORT } else { "5899" }
$Mode = if ($args.Count -gt 0) { $args[0].ToLower() } else { "both" }

function Write-Info([string]$Message) {
    Write-Host $Message -ForegroundColor Cyan
}

function Write-Warn([string]$Message) {
    Write-Host $Message -ForegroundColor Yellow
}

function Write-Err([string]$Message) {
    Write-Host $Message -ForegroundColor Red
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-Python {
    if (Test-Path $VenvPython) {
        return
    }

    if (-not (Test-Command "python")) {
        Write-Err "Python not found. Install Python 3.11+ from https://www.python.org/downloads/"
        exit 1
    }

    Write-Info "Creating virtual environment at .venv ..."
    & python -m venv (Join-Path $Root ".venv")
    if (-not (Test-Path $VenvPython)) {
        Write-Err "Failed to create .venv"
        exit 1
    }
}

function Ensure-Installed {
    Ensure-Python

    $pip = Join-Path $Root ".venv\Scripts\pip.exe"
    if (-not (Test-Path $VenvVibe)) {
        Write-Info "Installing vibe-trading-ai (editable) ..."
        & $pip install -e $Root
    }
}

function Ensure-EnvFile {
    if (Test-Path $EnvFile) {
        return
    }

    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Warn "Created agent/.env from .env.example - edit LLM API keys before use."
        return
    }

    Write-Warn "agent/.env not found. Create it and set LANGCHAIN_PROVIDER + API key."
}

function Ensure-FrontendDeps {
    $viteBin = Join-Path $FrontendDir "node_modules\.bin\vite.cmd"
    if (Test-Path $viteBin) {
        return
    }

    if (-not (Test-Command "npm")) {
        Write-Err "Node.js/npm not found. Install from https://nodejs.org/ then run: .\start-local.ps1 setup"
        exit 1
    }

    Write-Info "Installing frontend dependencies (npm install) ..."
    Push-Location $FrontendDir
    try {
        npm install
    } finally {
        Pop-Location
    }
}

function Start-Backend {
    Ensure-Installed
    Ensure-EnvFile
    Write-Info "Starting backend on http://127.0.0.1:$BackendPort ..."
    Write-Info "API docs: http://127.0.0.1:$BackendPort/docs"
    Set-Location $AgentDir
    & $VenvVibe serve --host 127.0.0.1 --port $BackendPort
}

function Start-Frontend {
    Ensure-FrontendDeps
    $env:VITE_API_URL = "http://127.0.0.1:$BackendPort"
    Write-Info "Starting frontend on http://127.0.0.1:$FrontendPort ..."
    Write-Info "Backend target: $env:VITE_API_URL"
    Set-Location $FrontendDir
    npm run dev -- --host 127.0.0.1 --port $FrontendPort
}

function Start-Both {
    Ensure-Installed
    Ensure-EnvFile
    Ensure-FrontendDeps
    Write-Info "Starting Vibe-Trading dev (backend + frontend) ..."
    Write-Info "  Web UI : http://127.0.0.1:$FrontendPort"
    Write-Info "  Backend: http://127.0.0.1:$BackendPort"
    Write-Info "Press Ctrl+C to stop both."
    Set-Location $AgentDir
    & $VenvVibe dev --port $BackendPort --frontend-port $FrontendPort --frontend-dir $FrontendDir
}

function Start-Setup {
    Ensure-Installed
    Ensure-EnvFile
    Ensure-FrontendDeps
    Write-Info "Setup complete."
    Write-Info "Next: edit agent/.env (LLM key), then run: .\start-local.ps1"
}

function Start-Docker {
    if (-not (Test-Command "docker")) {
        Write-Err "Docker not found. Install Docker Desktop or use .\start-local.ps1 both"
        exit 1
    }

    Ensure-EnvFile
    Write-Info "Starting Docker stack (backend on http://127.0.0.1:8899) ..."
    Set-Location $Root
    docker compose up -d --build
    Write-Info ""
    Write-Info "Backend: http://127.0.0.1:8899"
    Write-Info "Optional dev frontend: docker compose --profile frontend up -d"
}

function Start-Chat {
    Ensure-Installed
    Ensure-EnvFile
    Write-Info "Starting interactive CLI chat ..."
    Set-Location $AgentDir
    & $VenvVibe chat
}

function Show-Usage {
    @"
Vibe-Trading quick start (Windows)

Usage:
  .\start-local.ps1 [mode]

Modes:
  both      Start backend + frontend dev servers (default)
  backend   API only on port $BackendPort
  frontend  Web UI only on port $FrontendPort (backend must already run)
  setup     First-time install: venv, pip, npm
  docker    Docker Compose backend
  chat      Interactive terminal chat (no browser)
  help      Show this message

URLs (local dev):
  Web UI : http://127.0.0.1:$FrontendPort
  Backend: http://127.0.0.1:$BackendPort
  API doc: http://127.0.0.1:$BackendPort/docs

Config:
  Edit agent/.env - set LANGCHAIN_PROVIDER and API key (see agent/.env.example)
"@
}

switch ($Mode) {
    "help" { Show-Usage; exit 0 }
    "setup" { Start-Setup }
    "backend" { Start-Backend }
    "frontend" { Start-Frontend }
    "both" { Start-Both }
    "docker" { Start-Docker }
    "chat" { Start-Chat }
    default {
        Write-Err "Unknown mode: $Mode"
        Show-Usage
        exit 1
    }
}
